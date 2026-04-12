import time
import logging
import sys
import os
import gc
import json
import threading
import re
import sqlite3
from datetime import datetime

# Configuração de logging (sem arquivo para economizar disco no Render)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('Main')

import config
from modules import database
from modules.telegram_bot import AuctionTelegramBot
from modules.analyzer import AuctionAnalyzer
from modules.agenda import AgendaManager
from modules.post_auction import PostAuctionManager

# Importa os scrapers
from scrapers.govdeals import GovDealsScraper
from scrapers.publicsurplus import PublicSurplusScraper
from scrapers.bidspotter import BidSpotterScraper
from scrapers.avgear import AVGearScraper
from scrapers.jjkane import JJKaneScraper

# Flask para manter o serviço ativo no Render (plano gratuito requer porta HTTP)
from flask import Flask, jsonify

app = Flask(__name__)

# ==========================================
# REGISTRO DE LOGS EM MEMÓRIA (para o dashboard)
# ==========================================
MAX_LOG_ENTRIES = 200
_log_buffer = []
_log_lock = threading.Lock()


class DashboardLogHandler(logging.Handler):
    """Handler que armazena logs em memória para exibição no dashboard."""

    def emit(self, record):
        try:
            entry = {
                "time": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
            }
            with _log_lock:
                _log_buffer.append(entry)
                if len(_log_buffer) > MAX_LOG_ENTRIES:
                    _log_buffer.pop(0)
        except Exception:
            pass


# Adiciona o handler de dashboard ao root logger
_dashboard_handler = DashboardLogHandler()
_dashboard_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(_dashboard_handler)

# Timestamp de inicialização
_start_time = datetime.now()

# Contadores globais de atividade
_activity_counters = {
    "cycles_completed": 0,
    "items_found_total": 0,
    "items_found_this_cycle": 0,
    "alerts_sent": 0,
    "last_cycle_time": None,
    "errors_count": 0,
}
_counters_lock = threading.Lock()


class SearchRotator:
    """Gerencia a rotação de termos de busca entre ciclos.

    A cada ciclo (1 hora), seleciona um subconjunto de termos respeitando
    a ordem de prioridade (A -> B -> C) e rotaciona para o próximo bloco
    na hora seguinte. Isso distribui a carga e evita sobrecarregar os
    sites de leilão.
    """

    STATE_FILE = os.path.join(os.path.dirname(__file__), "database", "rotation_state.json")

    def __init__(self):
        # Monta a fila completa de (categoria, termo) na ordem de prioridade
        self._queue = []
        for _priority_label, category_list in config.ALL_PRIORITY_GROUPS:
            for category in category_list:
                terms = config.SEARCH_TERMS.get(category, [])
                for term in terms:
                    self._queue.append((category, term))

        self._offset = self._load_offset()
        logger.info(
            f"SearchRotator inicializado: {len(self._queue)} termos totais, "
            f"offset atual={self._offset}, termos/ciclo={config.TERMS_PER_CYCLE}"
        )

    # ------------------------------------------------------------------
    # Persistência do offset (sobrevive a reinícios do Render)
    # ------------------------------------------------------------------
    def _load_offset(self):
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, "r") as f:
                    data = json.load(f)
                return int(data.get("offset", 0)) % max(len(self._queue), 1)
        except Exception:
            pass
        return 0

    def _save_offset(self):
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
            with open(self.STATE_FILE, "w") as f:
                json.dump({"offset": self._offset, "updated": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.warning(f"Nao foi possivel salvar estado de rotacao: {e}")

    # ------------------------------------------------------------------
    # Seleção do bloco de termos para o ciclo atual
    # ------------------------------------------------------------------
    def next_batch(self):
        """Retorna uma lista de tuplas (category, term) para o ciclo atual."""
        total = len(self._queue)
        if total == 0:
            return []

        batch_size = min(config.TERMS_PER_CYCLE, total)
        batch = []
        for i in range(batch_size):
            idx = (self._offset + i) % total
            batch.append(self._queue[idx])

        # Avança o offset para o próximo ciclo
        self._offset = (self._offset + batch_size) % total
        self._save_offset()

        categories_in_batch = set(cat for cat, _ in batch)
        logger.info(
            f"Ciclo de busca: {batch_size} termos de {len(categories_in_batch)} categorias "
            f"(proximo offset={self._offset})"
        )
        return batch


class AuctionAgent:
    """Agente principal que coordena todos os módulos.
    Otimizado para Render Free (512MB RAM) — sem Selenium.
    """

    def __init__(self):
        logger.info("Inicializando Agente de Leiloes (modo leve — sem Selenium)...")

        # Inicializa banco de dados
        database.init_db()

        # Inicializa módulos
        self.bot = AuctionTelegramBot()
        self.analyzer = AuctionAnalyzer()
        self.agenda = AgendaManager(self.bot)
        self.post_auction = PostAuctionManager(self.bot)

        # Rotação de termos de busca
        self.rotator = SearchRotator()

        # Scrapers são instanciados sob demanda para economizar memória
        self._scraper_classes = [
            GovDealsScraper,
            PublicSurplusScraper,
            BidSpotterScraper,
            AVGearScraper,
            JJKaneScraper,
        ]

    def start(self):
        """Inicia o agente e todos os seus serviços."""
        logger.info("Iniciando servicos do agente...")

        # Inicia o bot do Telegram
        self.bot.start_polling()

        # Inicia o gerenciador de agenda
        self.agenda.start()

        # Inicia o gerenciador de pós-arrematação
        self.post_auction.start()

        # Inicia loop de monitoramento em thread separada
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()

        logger.info("Todos os servicos iniciados com sucesso.")

    def _monitoring_loop(self):
        """Loop principal que executa os scrapers periodicamente."""
        logger.info(f"Iniciando loop de monitoramento (intervalo: {config.CHECK_INTERVAL}s)")

        while True:
            try:
                self._run_scrapers()
                with _counters_lock:
                    _activity_counters["cycles_completed"] += 1
                    _activity_counters["last_cycle_time"] = datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")
                with _counters_lock:
                    _activity_counters["errors_count"] += 1

            # Força coleta de lixo após cada rodada
            gc.collect()

            logger.info(f"Aguardando {config.CHECK_INTERVAL} segundos para a proxima verificacao...")
            time.sleep(config.CHECK_INTERVAL)

    def _run_scrapers(self):
        """Executa os scrapers para o bloco de termos do ciclo atual.

        Usa o SearchRotator para obter o subconjunto de termos e itera
        sobre cada scraper, respeitando o delay entre requisições.
        """
        batch = self.rotator.next_batch()
        if not batch:
            logger.warning("Nenhum termo de busca configurado.")
            return

        logger.info(f"Iniciando rodada de scraping com {len(batch)} termos...")
        total_found = 0

        with _counters_lock:
            _activity_counters["items_found_this_cycle"] = 0

        for category, keyword in batch:
            for scraper_class in self._scraper_classes:
                scraper = None
                try:
                    # Instancia o scraper sob demanda
                    scraper = scraper_class()

                    # Busca itens
                    items = scraper.search(keyword)

                    # Processa cada item encontrado
                    for item in items:
                        # Adiciona metadados de categoria e prioridade
                        item["category"] = category
                        item["priority"] = self._get_priority(category)
                        self._process_item(item, category)
                        total_found += 1

                except Exception as e:
                    site_name = scraper.site_name if scraper else scraper_class.__name__
                    logger.error(f"Erro ao executar scraper {site_name} para '{keyword}': {e}")
                    with _counters_lock:
                        _activity_counters["errors_count"] += 1
                finally:
                    # Libera o scraper da memória
                    if scraper:
                        scraper.session.close()
                        del scraper
                    gc.collect()

                # Delay entre requisições para evitar bloqueio
                time.sleep(config.REQUEST_DELAY)

        with _counters_lock:
            _activity_counters["items_found_total"] += total_found
            _activity_counters["items_found_this_cycle"] = total_found

        logger.info(f"Rodada concluida: {total_found} itens encontrados no total.")

    @staticmethod
    def _get_priority(category):
        """Retorna a letra de prioridade (A/B/C) de uma categoria."""
        if category in config.PRIORITY_A:
            return "A"
        if category in config.PRIORITY_B:
            return "B"
        if category in config.PRIORITY_C:
            return "C"
        return "C"

    def _process_item(self, item, category):
        """Processa um item encontrado, analisa e envia alerta se necessário."""
        item_id = item["id"]

        # Verifica se já foi notificado
        if database.is_item_notified(item_id):
            return

        # Filtra por preço máximo da categoria (se o preço for legível)
        max_price = config.MAX_PRICE.get(category)
        if max_price and item.get("price"):
            numeric_price = self._parse_price(item["price"])
            if numeric_price and numeric_price > max_price:
                logger.info(
                    f"Item ignorado (preco ${numeric_price:,.0f} > max ${max_price:,} "
                    f"para {category}): {item['title']}"
                )
                return

        logger.info(f"Novo item encontrado: {item['title']} ({item['site']}) [cat={category}]")

        # Analisa o item com LLM
        analysis = self.analyzer.analyze_item(
            title=item["title"],
            price=item["price"],
            site=item["site"],
            keyword=item["keyword"],
        )

        # Se a recomendação for boa, envia alerta
        if analysis.get("recommendation") in ["OTIMA OPORTUNIDADE", "BOA OPORTUNIDADE"]:
            self.bot.send_alert(item, analysis)
            with _counters_lock:
                _activity_counters["alerts_sent"] += 1

        # Marca como notificado para não enviar novamente
        database.mark_item_notified(
            item_id=item_id,
            site=item["site"],
            title=item["title"],
            link=item["link"],
            price=item["price"],
        )

    @staticmethod
    def _parse_price(price_str):
        """Extrai valor numérico de uma string de preço."""
        if not price_str or price_str == "Consultar no site":
            return None
        match = re.search(r'[\d,]+\.?\d*', str(price_str).replace(",", ""))
        if match:
            try:
                return float(match.group().replace(",", ""))
            except ValueError:
                return None
        return None


# ==========================================
# ROTAS FLASK (para manter o Render ativo)
# ==========================================
agent = None


@app.route("/")
def home():
    """Rota principal — health check."""
    total_terms = sum(len(v) for v in config.SEARCH_TERMS.values())
    return jsonify({
        "status": "running",
        "service": "Agente de Leiloes Americanos",
        "version": "4.0-dashboard",
        "memory_mode": "optimized (no Selenium)",
        "total_search_terms": total_terms,
        "categories": len(config.SEARCH_TERMS),
        "terms_per_cycle": config.TERMS_PER_CYCLE,
        "check_interval_seconds": config.CHECK_INTERVAL,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/health")
def health():
    """Health check para o Render."""
    return jsonify({"status": "healthy"}), 200


@app.route("/stats")
def stats():
    """Retorna estatísticas do agente."""
    try:
        stats_data = database.get_dashboard_stats()
        return jsonify({"status": "ok", "stats": stats_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/categories")
def categories():
    """Lista todas as categorias e quantidade de termos."""
    cat_info = {}
    for cat, terms in config.SEARCH_TERMS.items():
        priority = "A" if cat in config.PRIORITY_A else "B" if cat in config.PRIORITY_B else "C"
        cat_info[cat] = {
            "terms_count": len(terms),
            "priority": priority,
            "max_price_usd": config.MAX_PRICE.get(cat, "N/A"),
        }
    return jsonify({
        "total_categories": len(cat_info),
        "total_terms": sum(len(v) for v in config.SEARCH_TERMS.values()),
        "categories": cat_info,
    })


# ==========================================
# DASHBOARD WEB — /dashboard
# ==========================================

def _get_db_items(limit=50):
    """Busca os últimos itens no banco de dados SQLite."""
    items = []
    try:
        db_path = config.DB_PATH
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Tenta buscar da tabela de itens notificados
            try:
                cursor.execute(
                    "SELECT * FROM notified_items ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                for row in rows:
                    items.append(dict(row))
            except sqlite3.OperationalError:
                # Tabela pode ter nome diferente — tenta alternativas
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [r[0] for r in cursor.fetchall()]
                for table in tables:
                    if "item" in table.lower() or "auction" in table.lower() or "notif" in table.lower():
                        try:
                            cursor.execute(
                                f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?",
                                (limit,),
                            )
                            rows = cursor.fetchall()
                            for row in rows:
                                items.append(dict(row))
                            if items:
                                break
                        except Exception:
                            continue
            conn.close()
    except Exception as e:
        logger.error(f"Erro ao buscar itens do banco: {e}")
    return items


def _get_financial_data():
    """Busca dados financeiros do banco de dados."""
    data = {
        "total_invested": 0,
        "total_sold": 0,
        "profit": 0,
        "items_in_stock": 0,
        "items_sold": 0,
        "items_tracked": 0,
    }
    try:
        db_path = config.DB_PATH
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # Busca tabelas financeiras
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]

            for table in tables:
                tl = table.lower()
                if "purchase" in tl or "invest" in tl or "bought" in tl:
                    try:
                        cursor.execute(f"SELECT SUM(price) FROM {table}")
                        result = cursor.fetchone()
                        if result and result[0]:
                            data["total_invested"] = float(result[0])
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        result = cursor.fetchone()
                        if result:
                            data["items_in_stock"] = int(result[0])
                    except Exception:
                        pass

                if "sale" in tl or "sold" in tl:
                    try:
                        cursor.execute(f"SELECT SUM(price) FROM {table}")
                        result = cursor.fetchone()
                        if result and result[0]:
                            data["total_sold"] = float(result[0])
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        result = cursor.fetchone()
                        if result:
                            data["items_sold"] = int(result[0])
                    except Exception:
                        pass

                if "notif" in tl or "item" in tl or "track" in tl:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        result = cursor.fetchone()
                        if result:
                            data["items_tracked"] = int(result[0])
                    except Exception:
                        pass

            conn.close()
            data["profit"] = data["total_sold"] - data["total_invested"]
    except Exception as e:
        logger.error(f"Erro ao buscar dados financeiros: {e}")
    return data


def _build_dashboard_html():
    """Gera o HTML completo do dashboard."""
    now = datetime.now()
    uptime = now - _start_time
    uptime_str = f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m"

    total_terms = sum(len(v) for v in config.SEARCH_TERMS.values())
    total_categories = len(config.SEARCH_TERMS)

    # Dados de atividade
    with _counters_lock:
        counters = dict(_activity_counters)

    # Dados financeiros
    fin = _get_financial_data()

    # Itens recentes do banco
    db_items = _get_db_items(30)

    # Logs recentes
    with _log_lock:
        recent_logs = list(_log_buffer[-50:])
    recent_logs.reverse()

    # Monta os cards de categorias
    category_groups = {
        "Allen & Heath": [],
        "Shure Axient": [],
        "Lighting": [],
        "LED / Video": [],
        "Golf Carts": [],
        "Combos": [],
        "Oportunidades": [],
    }

    for cat_name, terms in config.SEARCH_TERMS.items():
        priority = "A" if cat_name in config.PRIORITY_A else "B" if cat_name in config.PRIORITY_B else "C"
        max_p = config.MAX_PRICE.get(cat_name, 0)
        entry = {"name": cat_name, "count": len(terms), "priority": priority, "max_price": max_p}

        cn = cat_name.lower()
        if "allen" in cn:
            category_groups["Allen & Heath"].append(entry)
        elif "shure" in cn:
            category_groups["Shure Axient"].append(entry)
        elif "light" in cn:
            category_groups["Lighting"].append(entry)
        elif "led" in cn:
            category_groups["LED / Video"].append(entry)
        elif "golf" in cn:
            category_groups["Golf Carts"].append(entry)
        elif "combo" in cn:
            category_groups["Combos"].append(entry)
        else:
            category_groups["Oportunidades"].append(entry)

    # Gera HTML dos cards de categorias
    cat_cards_html = ""
    group_icons = {
        "Allen & Heath": "🎛",
        "Shure Axient": "🎤",
        "Lighting": "💡",
        "LED / Video": "📺",
        "Golf Carts": "🏌",
        "Combos": "📦",
        "Oportunidades": "🔍",
    }

    for group_name, entries in category_groups.items():
        if not entries:
            continue
        icon = group_icons.get(group_name, "📋")
        group_total = sum(e["count"] for e in entries)
        sub_items = ""
        for e in entries:
            pbadge_color = "#00e676" if e["priority"] == "A" else "#ffc107" if e["priority"] == "B" else "#ff5722"
            cat_id = e["name"].replace(" ", "_").lower()
            sub_items += (
                f'<div class="cat-sub-item" data-category="{e["name"]}" onclick="toggleCategory(this, event)" style="cursor:pointer">'
                f'<span class="cat-sub-toggle">▶</span>'
                f'<span class="cat-sub-name">{e["name"].replace("_", " ").title()}</span>'
                f'<span class="cat-sub-meta">'
                f'<span class="priority-badge" style="background:{pbadge_color}">{e["priority"]}</span>'
                f'{e["count"]} termos'
                f'</span>'
                f'</div>'
                f'<div class="cat-sub-details" id="details-{cat_id}" style="display:none;padding:10px 20px;background:#1c2128;border-left:3px solid {pbadge_color};max-height:0;overflow:hidden;transition:max-height 0.3s ease">'
                f'<div class="loading" style="text-align:center;color:#8b949e;font-size:12px">Carregando...</div>'
                f'</div>'
            )
        cat_cards_html += (
            f'<div class="category-card">'
            f'<div class="cat-card-header">'
            f'<span class="cat-icon">{icon}</span>'
            f'<span class="cat-group-name">{group_name}</span>'
            f'<span class="cat-group-total">{group_total} termos</span>'
            f'</div>'
            f'<div class="cat-sub-list">{sub_items}</div>'
            f'</div>'
        )

    # Gera HTML da tabela de itens
    items_rows = ""
    if db_items:
        for item in db_items[:30]:
            title = item.get("title", item.get("name", "N/A"))
            site = item.get("site", "N/A")
            price = item.get("price", "N/A")
            link = item.get("link", item.get("url", "#"))
            # Trunca título longo
            if len(str(title)) > 70:
                title = str(title)[:67] + "..."
            items_rows += (
                f'<tr>'
                f'<td class="td-title">{title}</td>'
                f'<td>{site}</td>'
                f'<td class="td-price">{price}</td>'
                f'<td><span class="status-active">Notificado</span></td>'
                f'<td><a href="{link}" target="_blank" class="link-btn">Ver</a></td>'
                f'</tr>'
            )
    else:
        items_rows = (
            '<tr><td colspan="5" class="no-data">'
            'Nenhum item encontrado ainda. O agente esta buscando...'
            '</td></tr>'
        )

    # Gera HTML dos logs
    logs_html = ""
    for log in recent_logs[:40]:
        level = log["level"]
        lclass = "log-info" if level == "INFO" else "log-warn" if level == "WARNING" else "log-error" if level == "ERROR" else "log-debug"
        msg = log["message"]
        if len(msg) > 120:
            msg = msg[:117] + "..."
        logs_html += (
            f'<div class="log-entry {lclass}">'
            f'<span class="log-time">{log["time"]}</span>'
            f'<span class="log-level">[{level}]</span>'
            f'<span class="log-msg">{msg}</span>'
            f'</div>'
        )
    if not logs_html:
        logs_html = '<div class="log-entry log-info"><span class="log-msg">Aguardando logs...</span></div>'

    # Status do agente
    agent_status = "Ativo" if agent else "Inicializando"
    status_color = "#00e676" if agent else "#ffc107"

    # Ciclos estimados para cobrir todos os termos
    cycles_to_cover = (total_terms + config.TERMS_PER_CYCLE - 1) // config.TERMS_PER_CYCLE

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Agente de Leiloes R33 - Painel de Controle</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}}
a{{color:#58a6ff;text-decoration:none}}
a:hover{{text-decoration:underline}}

/* Header */
.header{{background:linear-gradient(135deg,#161b22 0%,#1a2332 100%);border-bottom:1px solid #30363d;padding:20px 30px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}}
.header-left{{display:flex;align-items:center;gap:15px}}
.logo{{font-size:28px;font-weight:700;color:#f0f6fc;letter-spacing:-0.5px}}
.logo span{{color:#58a6ff}}
.header-badge{{background:#238636;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}}
.header-right{{display:flex;align-items:center;gap:15px;font-size:13px;color:#8b949e}}
.header-right .dot{{width:8px;height:8px;border-radius:50%;display:inline-block}}

/* Container */
.container{{max-width:1400px;margin:0 auto;padding:20px}}

/* Section titles */
.section-title{{font-size:18px;font-weight:600;color:#f0f6fc;margin:30px 0 15px;padding-bottom:8px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px}}
.section-title:first-child{{margin-top:0}}

/* Overview cards */
.overview-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-bottom:25px}}
.overview-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;transition:border-color 0.2s}}
.overview-card:hover{{border-color:#58a6ff}}
.ov-label{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px}}
.ov-value{{font-size:28px;font-weight:700;color:#f0f6fc}}
.ov-value.green{{color:#3fb950}}
.ov-value.blue{{color:#58a6ff}}
.ov-value.orange{{color:#d29922}}
.ov-value.red{{color:#f85149}}
.ov-sub{{font-size:11px;color:#8b949e;margin-top:4px}}

/* Category cards */
.categories-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px;margin-bottom:25px}}
.category-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;transition:border-color 0.2s}}
.category-card:hover{{border-color:#58a6ff}}
.cat-card-header{{display:flex;align-items:center;gap:10px;padding:15px 18px;background:#1c2333;border-bottom:1px solid #30363d}}
.cat-icon{{font-size:22px}}
.cat-group-name{{font-weight:600;color:#f0f6fc;flex:1}}
.cat-group-total{{font-size:12px;color:#8b949e;background:#21262d;padding:3px 10px;border-radius:10px}}
.cat-sub-list{{padding:10px 18px}}
.cat-sub-item{{display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #21262d}}
.cat-sub-item:last-child{{border-bottom:none}}
.cat-sub-name{{font-size:13px;color:#c9d1d9}}
.cat-sub-meta{{display:flex;align-items:center;gap:8px;font-size:12px;color:#8b949e}}
.priority-badge{{display:inline-block;width:22px;height:22px;border-radius:50%;text-align:center;line-height:22px;font-size:11px;font-weight:700;color:#0d1117}}

/* Financial cards */
.finance-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px;margin-bottom:25px}}
.fin-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px;text-align:center}}
.fin-card .fin-icon{{font-size:28px;margin-bottom:8px}}
.fin-card .fin-label{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px}}
.fin-card .fin-value{{font-size:24px;font-weight:700;margin-top:5px}}

/* Table */
.table-wrap{{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;margin-bottom:25px}}
.table-wrap table{{width:100%;border-collapse:collapse}}
.table-wrap th{{background:#1c2333;padding:12px 15px;text-align:left;font-size:12px;text-transform:uppercase;color:#8b949e;letter-spacing:0.5px;border-bottom:1px solid #30363d}}
.table-wrap td{{padding:10px 15px;border-bottom:1px solid #21262d;font-size:13px}}
.table-wrap tr:last-child td{{border-bottom:none}}
.table-wrap tr:hover{{background:#1c2128}}
.td-title{{max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#f0f6fc}}
.td-price{{color:#3fb950;font-weight:600}}
.status-active{{background:#238636;color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600}}
.link-btn{{background:#21262d;color:#58a6ff;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;transition:background 0.2s}}
.link-btn:hover{{background:#30363d;text-decoration:none}}
.no-data{{text-align:center;color:#8b949e;padding:30px!important;font-style:italic}}

/* Logs */
.logs-container{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:15px;max-height:400px;overflow-y:auto;margin-bottom:25px;font-family:'Cascadia Code','Fira Code','Consolas',monospace}}
.log-entry{{padding:4px 8px;font-size:12px;line-height:1.6;border-radius:4px;margin-bottom:2px;display:flex;gap:10px;flex-wrap:wrap}}
.log-entry:hover{{background:#1c2128}}
.log-time{{color:#484f58;min-width:140px}}
.log-level{{font-weight:600;min-width:60px}}
.log-msg{{flex:1;word-break:break-all}}
.log-info .log-level{{color:#58a6ff}}
.log-warn .log-level{{color:#d29922}}
.log-error .log-level{{color:#f85149}}
.log-debug .log-level{{color:#8b949e}}

/* Footer */
.footer{{text-align:center;padding:20px;color:#484f58;font-size:12px;border-top:1px solid #21262d;margin-top:20px}}

/* Scrollbar */
::-webkit-scrollbar{{width:8px}}
::-webkit-scrollbar-track{{background:#0d1117}}
::-webkit-scrollbar-thumb{{background:#30363d;border-radius:4px}}
::-webkit-scrollbar-thumb:hover{{background:#484f58}}

/* Expandable categories */
.cat-sub-item{{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #21262d;transition:background 0.2s;user-select:none}}
.cat-sub-item:last-of-type{{border-bottom:none}}
.cat-sub-item:hover{{background:#1c2128}}
.cat-sub-toggle{{display:inline-block;width:16px;text-align:center;color:#8b949e;font-size:12px;transition:transform 0.3s ease;margin-right:8px}}
.cat-sub-item.expanded .cat-sub-toggle{{transform:rotate(90deg)}}
.cat-sub-name{{flex:1;color:#c9d1d9;font-size:13px}}
.cat-sub-meta{{display:flex;align-items:center;gap:8px;font-size:12px;color:#8b949e}}

.cat-sub-details{{background:#1c2128;border-left:3px solid #58a6ff;padding:15px;margin-top:5px;border-radius:6px}}
.cat-sub-details.expanded{{max-height:2000px!important}}

.term-list{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:15px}}
.term-item{{background:#161b22;border:1px solid #30363d;padding:10px;border-radius:6px;font-size:12px;cursor:pointer;transition:border-color 0.2s}}
.term-item:hover{{border-color:#58a6ff}}
.term-name{{color:#f0f6fc;font-weight:500;margin-bottom:5px}}
.term-count{{color:#8b949e;font-size:11px}}

.items-table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px}}
.items-table th{{background:#161b22;padding:8px;text-align:left;color:#8b949e;border-bottom:1px solid #30363d;font-weight:600}}
.items-table td{{padding:8px;border-bottom:1px solid #21262d;color:#c9d1d9}}
.items-table tr:hover{{background:#1c2128}}
.items-table .item-title{{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.items-table .item-price{{color:#3fb950;font-weight:600}}
.items-table .item-site{{color:#58a6ff;font-size:11px}}
.items-table .item-link{{color:#58a6ff;text-decoration:underline;cursor:pointer}}

.no-items{{color:#8b949e;font-style:italic;padding:10px;text-align:center;font-size:12px}}
.loading{{color:#8b949e;font-size:12px;text-align:center;padding:10px}}

/* Responsive */
@media(max-width:768px){{
    .header{{padding:15px}}
    .logo{{font-size:20px}}
    .container{{padding:10px}}
    .overview-grid{{grid-template-columns:repeat(2,1fr)}}
    .categories-grid{{grid-template-columns:1fr}}
    .finance-grid{{grid-template-columns:repeat(2,1fr)}}
    .table-wrap{{overflow-x:auto}}
    .table-wrap table{{min-width:600px}}
    .ov-value{{font-size:22px}}
    .term-list{{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}
}}
@media(max-width:480px){{
    .overview-grid{{grid-template-columns:1fr}}
    .finance-grid{{grid-template-columns:1fr}}
    .term-list{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div class="header-left">
        <div class="logo">Agente de Leiloes <span>R33</span></div>
        <span class="header-badge">Painel de Controle</span>
    </div>
    <div class="header-right">
        <span class="dot" style="background:{status_color}"></span>
        <span>{agent_status}</span>
        <span>|</span>
        <span>Atualizado: {now.strftime("%d/%m/%Y %H:%M:%S")}</span>
        <span>|</span>
        <span>Auto-refresh: 60s</span>
    </div>
</div>

<div class="container">

    <!-- VISAO GERAL -->
    <div class="section-title">Visao Geral</div>
    <div class="overview-grid">
        <div class="overview-card">
            <div class="ov-label">Status</div>
            <div class="ov-value green">{agent_status}</div>
            <div class="ov-sub">Uptime: {uptime_str}</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Total de Termos</div>
            <div class="ov-value blue">{total_terms}</div>
            <div class="ov-sub">{total_categories} categorias</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Termos por Ciclo</div>
            <div class="ov-value">{config.TERMS_PER_CYCLE}</div>
            <div class="ov-sub">{cycles_to_cover} ciclos para cobrir tudo</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Intervalo</div>
            <div class="ov-value">{config.CHECK_INTERVAL // 60} min</div>
            <div class="ov-sub">{config.CHECK_INTERVAL}s entre ciclos</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Ciclos Completos</div>
            <div class="ov-value blue">{counters["cycles_completed"]}</div>
            <div class="ov-sub">Ultimo: {counters["last_cycle_time"] or "Aguardando..."}</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Itens Encontrados</div>
            <div class="ov-value green">{counters["items_found_total"]}</div>
            <div class="ov-sub">Este ciclo: {counters["items_found_this_cycle"]}</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Alertas Enviados</div>
            <div class="ov-value orange">{counters["alerts_sent"]}</div>
            <div class="ov-sub">Via Telegram</div>
        </div>
        <div class="overview-card">
            <div class="ov-label">Erros</div>
            <div class="ov-value red">{counters["errors_count"]}</div>
            <div class="ov-sub">Desde o inicio</div>
        </div>
    </div>

    <!-- DASHBOARD FINANCEIRO -->
    <div class="section-title">Dashboard Financeiro</div>
    <div class="finance-grid">
        <div class="fin-card">
            <div class="fin-icon">📊</div>
            <div class="fin-label">Itens Rastreados</div>
            <div class="fin-value" style="color:#58a6ff">{fin["items_tracked"]}</div>
        </div>
        <div class="fin-card">
            <div class="fin-icon">💰</div>
            <div class="fin-label">Total Investido</div>
            <div class="fin-value" style="color:#f85149">${fin["total_invested"]:,.2f}</div>
        </div>
        <div class="fin-card">
            <div class="fin-icon">🏷</div>
            <div class="fin-label">Total Vendido</div>
            <div class="fin-value" style="color:#3fb950">${fin["total_sold"]:,.2f}</div>
        </div>
        <div class="fin-card">
            <div class="fin-icon">📈</div>
            <div class="fin-label">Lucro</div>
            <div class="fin-value" style="color:{"#3fb950" if fin["profit"] >= 0 else "#f85149"}">${fin["profit"]:,.2f}</div>
        </div>
        <div class="fin-card">
            <div class="fin-icon">📦</div>
            <div class="fin-label">Em Estoque</div>
            <div class="fin-value" style="color:#d29922">{fin["items_in_stock"]}</div>
        </div>
        <div class="fin-card">
            <div class="fin-icon">✅</div>
            <div class="fin-label">Vendidos</div>
            <div class="fin-value" style="color:#3fb950">{fin["items_sold"]}</div>
        </div>
    </div>

    <!-- CATEGORIAS DE BUSCA -->
    <div class="section-title">Categorias de Busca ({total_categories} categorias, {total_terms} termos)</div>
    <div class="categories-grid">
        {cat_cards_html}
    </div>

    <!-- ULTIMOS LEILOES ENCONTRADOS -->
    <div class="section-title">Ultimos Leiloes Encontrados</div>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Titulo</th>
                    <th>Site</th>
                    <th>Preco</th>
                    <th>Status</th>
                    <th>Acao</th>
                </tr>
            </thead>
            <tbody>
                {items_rows}
            </tbody>
        </table>
    </div>

    <!-- LOGS RECENTES -->
    <div class="section-title">Logs Recentes dos Scrapers</div>
    <div class="logs-container">
        {logs_html}
    </div>

</div>

<!-- FOOTER -->
<div class="footer">
    Agente de Leiloes R33 v4.0 &mdash; Painel de Controle &mdash;
    {total_terms} termos em {total_categories} categorias &mdash;
    Render Free (512MB RAM) &mdash;
    {now.strftime("%d/%m/%Y %H:%M:%S")}
</div>

<script>
function toggleCategory(elem, event) {{
    event.stopPropagation();
    const categoryName = elem.getAttribute('data-category');
    const detailsId = 'details-' + categoryName.replace(/ /g, '_').toLowerCase();
    const detailsElem = document.getElementById(detailsId);
    
    if (!detailsElem) return;
    
    const isExpanded = elem.classList.contains('expanded');
    
    if (isExpanded) {{
        // Colapsar
        elem.classList.remove('expanded');
        detailsElem.classList.remove('expanded');
        detailsElem.style.maxHeight = '0';
    }} else {{
        // Expandir
        elem.classList.add('expanded');
        detailsElem.classList.add('expanded');
        
        // Carrega dados se ainda nao carregou
        if (detailsElem.querySelector('.loading')) {{
            loadCategoryData(categoryName, detailsElem);
        }}
        
        // Anima a expansao
        detailsElem.style.maxHeight = '2000px';
    }}
}}

function loadCategoryData(categoryName, detailsElem) {{
    // Busca dados da API
    fetch('/api/category/' + encodeURIComponent(categoryName))
        .then(response => response.json())
        .then(data => {{
            if (data.error) {{
                detailsElem.innerHTML = '<div class="no-items">Erro ao carregar dados</div>';
                return;
            }}
            
            let html = '';
            
            // Lista de termos
            html += '<div style="margin-bottom:15px">';
            html += '<div style="color:#f0f6fc;font-weight:600;margin-bottom:10px;font-size:13px">Termos de Busca (' + data.terms.length + ')</div>';
            html += '<div class="term-list">';
            
            data.terms.forEach(term => {{
                const itemCount = data.items_by_term[term] ? data.items_by_term[term].length : 0;
                html += '<div class="term-item">';
                html += '<div class="term-name">' + term + '</div>';
                html += '<div class="term-count">' + itemCount + ' item' + (itemCount !== 1 ? 'ns' : '') + ' encontrado' + (itemCount !== 1 ? 's' : '') + '</div>';
                html += '</div>';
            }});
            
            html += '</div>';
            html += '</div>';
            
            // Itens encontrados
            const hasItems = Object.keys(data.items_by_term).length > 0;
            if (hasItems) {{
                html += '<div style="margin-bottom:15px">';
                html += '<div style="color:#f0f6fc;font-weight:600;margin-bottom:10px;font-size:13px">Itens Encontrados</div>';
                html += '<table class="items-table">';
                html += '<thead><tr><th>Titulo</th><th>Preco</th><th>Site</th><th>Acao</th></tr></thead>';
                html += '<tbody>';
                
                for (const [term, items] of Object.entries(data.items_by_term)) {{
                    items.forEach(item => {{
                        const title = item.title || item.name || 'N/A';
                        const price = item.price || 'N/A';
                        const site = item.site || 'N/A';
                        const link = item.link || item.url || '#';
                        
                        html += '<tr>';
                        html += '<td class="item-title" title="' + title + '">' + title + '</td>';
                        html += '<td class="item-price">' + price + '</td>';
                        html += '<td class="item-site">' + site + '</td>';
                        html += '<td><a href="' + link + '" target="_blank" class="item-link">Ver</a></td>';
                        html += '</tr>';
                    }});
                }}
                
                html += '</tbody>';
                html += '</table>';
                html += '</div>';
            }} else {{
                html += '<div class="no-items">Nenhum item encontrado ainda para esta categoria</div>';
            }}
            
            detailsElem.innerHTML = html;
        }})
        .catch(error => {{
            console.error('Erro ao carregar categoria:', error);
            detailsElem.innerHTML = '<div class="no-items">Erro ao carregar dados: ' + error.message + '</div>';
        }});
}}
</script>

</body>
</html>"""
    return html


@app.route("/api/category/<category_name>")
def api_category(category_name):
    """
    API que retorna os termos de uma categoria e os itens encontrados.
    
    Retorna JSON com:
    - category: nome da categoria
    - priority: A/B/C
    - terms: lista de termos da categoria
    - items: lista de itens encontrados para cada termo
    """
    try:
        # Valida se a categoria existe
        if category_name not in config.SEARCH_TERMS:
            return jsonify({"error": "Categoria nao encontrada"}), 404
        
        terms = config.SEARCH_TERMS[category_name]
        priority = "A" if category_name in config.PRIORITY_A else "B" if category_name in config.PRIORITY_B else "C"
        max_price = config.MAX_PRICE.get(category_name, "N/A")
        
        # Busca itens do banco de dados para esta categoria
        items_by_term = {}
        try:
            db_path = config.DB_PATH
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Busca a tabela de itens
                try:
                    for term in terms:
                        cursor.execute(
                            "SELECT * FROM notified_items WHERE keyword = ? ORDER BY rowid DESC LIMIT 20",
                            (term,)
                        )
                        rows = cursor.fetchall()
                        if rows:
                            items_by_term[term] = [dict(row) for row in rows]
                except sqlite3.OperationalError:
                    # Tenta encontrar a tabela correta
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [r[0] for r in cursor.fetchall()]
                    for table in tables:
                        if "item" in table.lower() or "notif" in table.lower():
                            try:
                                for term in terms:
                                    cursor.execute(
                                        f"SELECT * FROM {table} WHERE keyword = ? ORDER BY rowid DESC LIMIT 20",
                                        (term,)
                                    )
                                    rows = cursor.fetchall()
                                    if rows:
                                        items_by_term[term] = [dict(row) for row in rows]
                            except Exception:
                                pass
                            break
                
                conn.close()
        except Exception as e:
            logger.error(f"Erro ao buscar itens para categoria {category_name}: {e}")
        
        return jsonify({
            "category": category_name,
            "priority": priority,
            "max_price": max_price,
            "terms_count": len(terms),
            "terms": terms,
            "items_by_term": items_by_term
        })
        
    except Exception as e:
        logger.error(f"Erro na API de categoria: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/dashboard")
def dashboard():
    """Dashboard web completo do agente de leiloes."""
    html = _build_dashboard_html()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ==========================================
# INICIALIZACAO
# ==========================================
def start_agent():
    """Inicializa o agente em background."""
    global agent
    try:
        agent = AuctionAgent()
        agent.start()
    except Exception as e:
        logger.critical(f"Erro fatal ao iniciar o agente: {e}")


if __name__ == "__main__":
    # Inicia o agente em uma thread separada
    agent_thread = threading.Thread(target=start_agent, daemon=True)
    agent_thread.start()

    # Inicia o servidor Flask
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Iniciando servidor Flask na porta {port}...")
    app.run(host="0.0.0.0", port=port)
