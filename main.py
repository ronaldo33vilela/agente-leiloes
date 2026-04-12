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

# Configuracao de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('Main')

import config
from modules import database
from modules.telegram_bot import AuctionTelegramBot
from modules.analyzer import AuctionAnalyzer
from modules.agenda import AgendaManager
from modules.post_auction import PostAuctionManager

from scrapers.govdeals import GovDealsScraper
from scrapers.publicsurplus import PublicSurplusScraper
from scrapers.bidspotter import BidSpotterScraper
from scrapers.avgear import AVGearScraper
from scrapers.jjkane import JJKaneScraper

from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://agente-leiloes.onrender.com/webhook')

# ==========================================
# REGISTRO DE LOGS EM MEMORIA (para o dashboard)
# ==========================================
MAX_LOG_ENTRIES = 200
_log_buffer = []
_log_lock = threading.Lock()


class DashboardLogHandler(logging.Handler):
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


_dashboard_handler = DashboardLogHandler()
_dashboard_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(_dashboard_handler)

_start_time = datetime.now()

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
    """Gerencia a rotacao de termos de busca entre ciclos."""

    STATE_FILE = os.path.join(os.path.dirname(__file__), "database", "rotation_state.json")

    def __init__(self):
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

    def next_batch(self):
        total = len(self._queue)
        if total == 0:
            return []
        batch_size = min(config.TERMS_PER_CYCLE, total)
        batch = []
        for i in range(batch_size):
            idx = (self._offset + i) % total
            batch.append(self._queue[idx])
        self._offset = (self._offset + batch_size) % total
        self._save_offset()
        categories_in_batch = set(cat for cat, _ in batch)
        logger.info(
            f"Ciclo de busca: {batch_size} termos de {len(categories_in_batch)} categorias "
            f"(proximo offset={self._offset})"
        )
        return batch


class AuctionAgent:
    """Agente principal que coordena todos os modulos."""

    def __init__(self):
        logger.info("Inicializando Agente de Leiloes (modo leve)...")
        database.init_db()
        self.bot = AuctionTelegramBot()
        self.analyzer = AuctionAnalyzer()
        self.agenda = AgendaManager(self.bot)
        self.post_auction = PostAuctionManager(self.bot)
        self.rotator = SearchRotator()
        self._scraper_classes = [
            GovDealsScraper,
            PublicSurplusScraper,
            BidSpotterScraper,
            AVGearScraper,
            JJKaneScraper,
        ]

    def start(self):
        logger.info("Iniciando servicos do agente...")
        # NAO usar polling - usamos webhook via Flask route /webhook
        # self.bot.start_polling()  # REMOVIDO: conflita com webhook
        self.agenda.start()
        self.post_auction.start()
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()
        logger.info("Todos os servicos iniciados com sucesso (modo webhook).")

    def _monitoring_loop(self):
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
            gc.collect()
            logger.info(f"Aguardando {config.CHECK_INTERVAL} segundos para a proxima verificacao...")
            time.sleep(config.CHECK_INTERVAL)

    def _run_scrapers(self):
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
                    scraper = scraper_class()
                    items = scraper.search(keyword)
                    for item in items:
                        item["category"] = category
                        item["priority"] = self._get_priority(category)
                        item["keyword"] = keyword
                        self._process_item(item, category)
                        total_found += 1
                except Exception as e:
                    site_name = scraper.site_name if scraper else scraper_class.__name__
                    logger.error(f"Erro ao executar scraper {site_name} para '{keyword}': {e}")
                    with _counters_lock:
                        _activity_counters["errors_count"] += 1
                finally:
                    if scraper:
                        scraper.session.close()
                        del scraper
                    gc.collect()
                time.sleep(config.REQUEST_DELAY)
        with _counters_lock:
            _activity_counters["items_found_total"] += total_found
            _activity_counters["items_found_this_cycle"] = total_found
        logger.info(f"Rodada concluida: {total_found} itens encontrados no total.")

    @staticmethod
    def _get_priority(category):
        if category in config.PRIORITY_A:
            return "A"
        if category in config.PRIORITY_B:
            return "B"
        if category in config.PRIORITY_C:
            return "C"
        return "C"

    def _process_item(self, item, category):
        item_id = item["id"]
        if database.is_item_notified(item_id):
            return

        # Filtra por preco maximo da categoria
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
            keyword=item.get("keyword", ""),
        )

        # Comparacao com historico de precos
        try:
            numeric_price = self._parse_price(item.get("price", "0")) or 0
            history_comparison = self.post_auction.compare_with_history(item["title"], numeric_price)
            if history_comparison:
                analysis["history_comparison"] = history_comparison
        except Exception:
            pass

        # Se a recomendacao for boa, envia alerta
        if analysis.get("recommendation") in ["OTIMA OPORTUNIDADE", "BOA OPORTUNIDADE"]:
            self.bot.send_alert(item, analysis)
            with _counters_lock:
                _activity_counters["alerts_sent"] += 1

        # Marca como notificado
        database.mark_item_notified(
            item_id=item_id,
            site=item["site"],
            title=item["title"],
            link=item["link"],
            price=item["price"],
            keyword=item.get("keyword", ""),
            category=category,
        )

        # Registra no historico de precos
        try:
            self.post_auction.collect_notified_item_price(item)
        except Exception:
            pass

    @staticmethod
    def _parse_price(price_str):
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
# ROTAS FLASK
# ==========================================
agent = None


@app.route("/")
def home():
    total_terms = sum(len(v) for v in config.SEARCH_TERMS.values())
    return jsonify({
        "status": "running",
        "service": "Agente de Leiloes R33",
        "version": "5.0-gestao-completa",
        "memory_mode": "optimized (no Selenium)",
        "total_search_terms": total_terms,
        "categories": len(config.SEARCH_TERMS),
        "terms_per_cycle": config.TERMS_PER_CYCLE,
        "check_interval_seconds": config.CHECK_INTERVAL,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/stats")
def stats():
    try:
        stats_data = database.get_dashboard_stats()
        return jsonify({"status": "ok", "stats": stats_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/categories")
def categories():
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


@app.route("/api/category/<category_name>")
def api_category(category_name):
    try:
        if category_name not in config.SEARCH_TERMS:
            return jsonify({"error": "Categoria nao encontrada"}), 404
        terms = config.SEARCH_TERMS[category_name]
        priority = "A" if category_name in config.PRIORITY_A else "B" if category_name in config.PRIORITY_B else "C"
        max_price = config.MAX_PRICE.get(category_name, "N/A")
        items_by_term = {}
        try:
            db_path = config.DB_PATH
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                try:
                    for term in terms:
                        # Busca por keyword E category para evitar dados cruzados
                        cursor.execute(
                            "SELECT * FROM notified_items WHERE keyword = ? AND category = ? ORDER BY rowid DESC LIMIT 20",
                            (term, category_name)
                        )
                        rows = cursor.fetchall()
                        if not rows:
                            # Fallback: busca apenas por keyword (compatibilidade)
                            cursor.execute(
                                "SELECT * FROM notified_items WHERE keyword = ? ORDER BY rowid DESC LIMIT 20",
                                (term,)
                            )
                            rows = cursor.fetchall()
                        if rows:
                            items_by_term[term] = [dict(row) for row in rows]
                except sqlite3.OperationalError:
                    pass
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


@app.route("/api/watchlist")
def api_watchlist():
    """API que retorna itens da watchlist."""
    try:
        status = "watching"
        items = database.get_watchlist_items(status)
        return jsonify({"status": "ok", "items": items, "count": len(items)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/price-history")
def api_price_history():
    """API que retorna historico de precos."""
    try:
        history = database.get_price_history(limit=100)
        stats = database.get_price_history_by_category_stats()
        return jsonify({"status": "ok", "history": history, "stats": stats, "count": len(history)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/watchlist/<int:item_id>/prices")
def api_watchlist_prices(item_id):
    """API que retorna historico de precos de um item da watchlist."""
    try:
        updates = database.get_price_updates(item_id)
        item = database.get_watchlist_item(item_id)
        return jsonify({"status": "ok", "item": item, "price_updates": updates})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# TELEGRAM WEBHOOK
# ==========================================

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Envia mensagem via API do Telegram."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN nao configurado")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem Telegram: {e}")
        return False


@app.route("/api/clear-data", methods=["POST"])
def clear_data():
    """Limpa TODOS os dados do banco de dados."""
    try:
        from modules.database import clear_notified_items, clear_watchlist, clear_price_history, get_connection
        
        # Limpar tabelas principais
        clear_notified_items()
        clear_watchlist()
        clear_price_history()
        
        # Limpar tabelas adicionais (won_items, inventory, agenda)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            for table in ['won_items', 'inventory', 'agenda']:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.commit()
            conn.close()
            logger.info("Tabelas adicionais limpas (won_items, inventory, agenda)")
        except Exception as e2:
            logger.warning(f"Aviso ao limpar tabelas adicionais: {e2}")
        
        # Resetar contadores em memoria
        global _activity_counters
        with _counters_lock:
            _activity_counters["items_found_total"] = 0
            _activity_counters["items_found_this_cycle"] = 0
            _activity_counters["alerts_sent"] = 0
            _activity_counters["errors_count"] = 0
        
        logger.info("TODOS os dados foram limpos com sucesso")
        return jsonify({
            "status": "success",
            "message": "Todos os dados foram limpos com sucesso. Pronto para começar do zero!"
        }), 200
    except Exception as e:
        logger.error(f"Erro ao limpar dados: {e}")
        return jsonify({
            "status": "error",
            "message": f"Erro ao limpar dados: {str(e)}"
        }), 500

@app.route("/api/scan-now", methods=["POST"])
def scan_now():
    """Dispara uma varredura manual imediata em todas as plataformas."""
    try:
        logger.info("Varredura manual iniciada via dashboard...")
        
        # Dispara a busca em background (nao bloqueia a resposta)
        def run_manual_scan():
            try:
                # Executa um ciclo de busca
                agent._run_scrapers()
                logger.info("Varredura manual concluida com sucesso")
            except Exception as e:
                logger.error(f"Erro durante varredura manual: {e}")
        
        # Executa em thread separada para nao bloquear
        scan_thread = threading.Thread(target=run_manual_scan, daemon=True)
        scan_thread.start()
        
        return jsonify({
            "status": "success",
            "message": "Varredura manual iniciada. Aguarde os resultados..."
        }), 200
    except Exception as e:
        logger.error(f"Erro ao iniciar varredura manual: {e}")
        return jsonify({
            "status": "error",
            "message": f"Erro ao iniciar varredura: {str(e)}"
        }), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    """Recebe updates do Telegram e processa comandos."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"ok": True}), 200
        
        message = data.get("message", {})
        if not message:
            return jsonify({"ok": True}), 200
        
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        user_id = message.get("from", {}).get("id")
        
        if not chat_id or not text:
            return jsonify({"ok": True}), 200
        
        logger.info(f"Telegram: user_id={user_id}, chat_id={chat_id}, text={text[:50]}")
        
        # Processa comando
        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            response_text = None
            
            # /start
            if cmd == "/start":
                response_text = (
                    "Bem-vindo ao Agente de Leiloes R33!\n\n"
                    "Comandos disponiveis:\n"
                    "/agendar URL TETO - Adiciona leilao a agenda\n"
                    "/agenda - Lista leiloes monitorados\n"
                    "/teto ID VALOR - Altera teto\n"
                    "/cancelar ID - Remove da agenda\n"
                    "/arquivar ID - Move para arquivo\n"
                    "/arquivo [cat] - Lista arquivo\n"
                    "/historico PRODUTO - Historico de precos\n"
                    "/preco PRODUTO - Preco medio\n"
                    "/ganhou - Registra arrematacao\n"
                    "/frete ID | Transp | Rastreio - Registra frete\n"
                    "/rastrear - Status em transito\n"
                    "/entregue ID - Marca entregue\n"
                    "/estoque - Lista estoque\n"
                    "/vender ID VALOR - Registra venda\n"
                    "/dashboard - Resumo completo"
                )
            
            # /agenda
            elif cmd == "/agenda":
                try:
                    watchlist = database.get_watchlist_items("watching")
                    if not watchlist:
                        response_text = "Nenhum leilao na agenda. Use /agendar URL TETO"
                    else:
                        lines = ["<b>Agenda de Leiloes:</b>\n"]
                        for w in watchlist[:10]:
                            wid = w.get("id", "?")
                            title = w.get("title", "N/A")[:40]
                            price = w.get("current_price", 0) or 0
                            ceiling = w.get("max_price_ceiling", 0) or 0
                            lines.append(f"<b>#{wid}</b> {title}\nPreco: ${price:,.0f} | Teto: ${ceiling:,.0f}")
                        response_text = "\n\n".join(lines)
                except Exception as e:
                    response_text = f"Erro ao buscar agenda: {e}"
            
            # /agendar URL TETO
            elif cmd == "/agendar":
                if len(args) < 2:
                    response_text = "Uso: /agendar URL TETO\nExemplo: /agendar https://govdeals.com/item/123 3000"
                else:
                    url = args[0]
                    try:
                        teto = float(args[1])
                        # Tenta extrair titulo da URL (simplificado)
                        title = f"Leilao de {url.split('/')[-1]}"
                        site = url.split("/")[2] if "/" in url else "desconhecido"
                        
                        item_id = database.add_to_watchlist(
                            title=title,
                            url=url,
                            site=site,
                            category="agenda_manual",
                            current_price=0,
                            max_price_ceiling=teto,
                            closing_date=None,
                        )
                        response_text = f"Leilao adicionado a agenda!\nID: {item_id}\nTeto: ${teto:,.2f}\n\nUse /agenda para ver todos."
                    except ValueError:
                        response_text = "Teto deve ser um numero. Exemplo: /agendar URL 3000"
            
            # /teto ID VALOR
            elif cmd == "/teto":
                if len(args) < 2:
                    response_text = "Uso: /teto ID VALOR\nExemplo: /teto 5 2500"
                else:
                    try:
                        item_id = int(args[0])
                        new_teto = float(args[1])
                        database.update_watchlist_ceiling(item_id, new_teto)
                        response_text = f"Teto do item #{item_id} atualizado para ${new_teto:,.2f}"
                    except (ValueError, Exception) as e:
                        response_text = f"Erro ao atualizar teto: {e}"
            
            # /cancelar ID
            elif cmd == "/cancelar":
                if not args:
                    response_text = "Uso: /cancelar ID"
                else:
                    try:
                        item_id = int(args[0])
                        database.remove_from_watchlist(item_id)
                        response_text = f"Leilao #{item_id} removido da agenda."
                    except Exception as e:
                        response_text = f"Erro: {e}"
            
            # /arquivar ID
            elif cmd == "/arquivar":
                if not args:
                    response_text = "Uso: /arquivar ID"
                else:
                    try:
                        item_id = int(args[0])
                        database.archive_watchlist_item(item_id)
                        response_text = f"Leilao #{item_id} movido para arquivo."
                    except Exception as e:
                        response_text = f"Erro: {e}"
            
            # /arquivo [categoria]
            elif cmd == "/arquivo":
                try:
                    archived = database.get_archived_items(limit=10)
                    if not archived:
                        response_text = "Nenhum leilao no arquivo."
                    else:
                        lines = ["<b>Arquivo de Leiloes:</b>\n"]
                        for a in archived[:10]:
                            aid = a.get("id", "?")
                            title = a.get("title", "N/A")[:35]
                            lines.append(f"<b>#{aid}</b> {title}")
                        response_text = "\n".join(lines)
                except Exception as e:
                    response_text = f"Erro: {e}"
            
            # /historico PRODUTO
            elif cmd == "/historico":
                if not args:
                    response_text = "Uso: /historico PRODUTO\nExemplo: /historico Allen Heath SQ5"
                else:
                    produto = " ".join(args)
                    try:
                        history = database.search_price_history(produto, limit=5)
                        if not history:
                            response_text = f"Nenhum historico encontrado para '{produto}'."
                        else:
                            lines = [f"<b>Historico: {produto}</b>\n"]
                            for h in history:
                                price = h.get("final_price", 0) or 0
                                date = h.get("closing_date", "N/A")[:10]
                                lines.append(f"${price:,.0f} em {date}")
                            response_text = "\n".join(lines)
                    except Exception as e:
                        response_text = f"Erro: {e}"
            
            # /preco PRODUTO
            elif cmd == "/preco":
                if not args:
                    response_text = "Uso: /preco PRODUTO"
                else:
                    produto = " ".join(args)
                    try:
                        avg = database.get_average_price(produto)
                        if avg:
                            response_text = f"Preco medio de <b>{produto}</b>: <b>${avg:,.2f}</b>"
                        else:
                            response_text = f"Nenhum dado de preco para '{produto}'."
                    except Exception as e:
                        response_text = f"Erro: {e}"
            
            # /dashboard
            elif cmd == "/dashboard":
                try:
                    stats = database.get_dashboard_stats()
                    response_text = (
                        f"<b>Dashboard Financeiro</b>\n\n"
                        f"Investido: ${stats.get('total_investido', 0):,.2f}\n"
                        f"Vendas: ${stats.get('total_vendas', 0):,.2f}\n"
                        f"Lucro: ${stats.get('lucro_acumulado', 0):,.2f}\n"
                        f"Em Estoque: {stats.get('em_estoque', 0)} itens\n"
                        f"Vendidos: {stats.get('vendidos', 0)} itens\n\n"
                        f"Acesse o dashboard web:\nhttps://agente-leiloes.onrender.com/dashboard"
                    )
                except Exception as e:
                    response_text = f"Erro: {e}"
            
            # Comando desconhecido
            else:
                response_text = f"Comando desconhecido: {cmd}\nUse /start para ver comandos disponiveis."
            
            if response_text:
                send_telegram_message(chat_id, response_text)
        
        return jsonify({"ok": True}), 200
    
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"ok": True}), 200


def setup_webhook():
    """Configura o webhook do Telegram na inicializacao."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN nao configurado, webhook nao sera configurado")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        payload = {"url": WEBHOOK_URL}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Webhook Telegram configurado: {WEBHOOK_URL}")
        else:
            logger.warning(f"Erro ao configurar webhook: {resp.text}")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")


# ==========================================
# DASHBOARD WEB — /dashboard
# ==========================================

def _get_db_items(limit=50):
    items = []
    try:
        db_path = config.DB_PATH
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT * FROM notified_items ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                for row in rows:
                    items.append(dict(row))
            except sqlite3.OperationalError:
                pass
            conn.close()
    except Exception as e:
        logger.error(f"Erro ao buscar itens do banco: {e}")
    return items


def _get_financial_data():
    data = {
        "total_invested": 0, "total_sold": 0, "profit": 0,
        "items_in_stock": 0, "items_sold": 0, "items_tracked": 0,
    }
    try:
        stats = database.get_dashboard_stats()
        data["total_invested"] = stats.get("total_investido", 0)
        data["total_sold"] = stats.get("total_vendas", 0)
        data["profit"] = stats.get("lucro_acumulado", 0)
        data["items_in_stock"] = stats.get("em_estoque", 0)
        data["items_sold"] = stats.get("vendidos", 0)
        data["items_tracked"] = stats.get("total_historico", 0)
    except Exception as e:
        logger.error(f"Erro ao buscar dados financeiros: {e}")
    return data


def _get_watchlist_items():
    try:
        return database.get_watchlist_items("watching")
    except Exception:
        return []


def _get_price_history_stats():
    try:
        return database.get_price_history_by_category_stats()
    except Exception:
        return []


def _build_dashboard_html():
    now = datetime.now()
    uptime = now - _start_time
    uptime_str = f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m"

    total_terms = sum(len(v) for v in config.SEARCH_TERMS.values())
    total_categories = len(config.SEARCH_TERMS)

    with _counters_lock:
        counters = dict(_activity_counters)

    fin = _get_financial_data()
    db_items = _get_db_items(30)
    watchlist = _get_watchlist_items()
    price_stats = _get_price_history_stats()

    with _log_lock:
        recent_logs = list(_log_buffer[-50:])
    recent_logs.reverse()

    # Monta cards de categorias
    category_groups = {
        "Allen & Heath": [], "Shure Axient": [], "Lighting": [],
        "LED / Video": [], "Golf Carts": [], "Combos": [], "Oportunidades": [],
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

    group_icons = {
        "Allen & Heath": "🎛", "Shure Axient": "🎤", "Lighting": "💡",
        "LED / Video": "📺", "Golf Carts": "🏌", "Combos": "📦", "Oportunidades": "🔍",
    }
    cat_cards_html = ""
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

    # Tabela de itens
    items_rows = ""
    if db_items:
        for item in db_items[:30]:
            title = item.get("title", item.get("name", "N/A"))
            site = item.get("site", "N/A")
            price = item.get("price", "N/A")
            link = item.get("link", item.get("url", "#"))
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
        items_rows = '<tr><td colspan="5" class="no-data">Nenhum item encontrado ainda. O agente esta buscando...</td></tr>'

    # Watchlist rows
    watchlist_rows = ""
    if watchlist:
        for w in watchlist[:20]:
            wt = w.get("title", "N/A")
            if len(str(wt)) > 55:
                wt = str(wt)[:52] + "..."
            wprice = w.get("current_price", 0) or 0
            wceiling = w.get("max_price_ceiling", 0) or 0
            wsite = w.get("site", "N/A")
            wurl = w.get("url", "#")
            wclose = str(w.get("closing_date", "N/A"))[:16] if w.get("closing_date") else "N/A"
            price_pct = (wprice / wceiling * 100) if wceiling > 0 else 0
            bar_color = "#3fb950" if price_pct < 70 else "#d29922" if price_pct < 90 else "#f85149"
            status_emoji = "🟢" if wprice <= wceiling else "🔴"
            watchlist_rows += (
                f'<tr>'
                f'<td>{w.get("id", "")}</td>'
                f'<td class="td-title">{wt}</td>'
                f'<td>{wsite}</td>'
                f'<td class="td-price">${wprice:,.2f}</td>'
                f'<td>${wceiling:,.2f} {status_emoji}</td>'
                f'<td>'
                f'<div style="background:#21262d;border-radius:4px;overflow:hidden;height:8px;width:80px">'
                f'<div style="background:{bar_color};height:100%;width:{min(price_pct, 100):.0f}%"></div>'
                f'</div>'
                f'<span style="font-size:10px;color:#8b949e">{price_pct:.0f}%</span>'
                f'</td>'
                f'<td>{wclose}</td>'
                f'<td><a href="{wurl}" target="_blank" class="link-btn">Ver</a></td>'
                f'</tr>'
            )
    else:
        watchlist_rows = '<tr><td colspan="8" class="no-data">Nenhum leilao na agenda. Use /agendar URL TETO no Telegram.</td></tr>'

    # Price history stats
    price_bars_html = ""
    if price_stats:
        for ps in price_stats[:15]:
            cat = ps.get("category", "N/A")
            avg = ps.get("avg_price", 0) or 0
            count = ps.get("total", 0) or 0
            min_p = ps.get("min_price", 0) or 0
            max_p = ps.get("max_price", 0) or 0
            bar_width = min(avg / 200, 100) if avg > 0 else 0  # Escala: $20k = 100%
            price_bars_html += (
                f'<div class="price-bar-row">'
                f'<div class="price-bar-label">{cat[:25]}</div>'
                f'<div class="price-bar-container">'
                f'<div class="price-bar-fill" style="width:{bar_width:.0f}%"></div>'
                f'</div>'
                f'<div class="price-bar-value">${avg:,.0f}</div>'
                f'<div class="price-bar-count">{count}x</div>'
                f'<div class="price-bar-range">${min_p:,.0f}-${max_p:,.0f}</div>'
                f'</div>'
            )
    else:
        price_bars_html = '<div class="no-data" style="padding:20px">Nenhum dado de historico ainda. Os precos serao coletados automaticamente.</div>'

    # Logs
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

    agent_status = "Ativo" if agent else "Inicializando"
    status_color = "#00e676" if agent else "#ffc107"
    cycles_to_cover = (total_terms + config.TERMS_PER_CYCLE - 1) // config.TERMS_PER_CYCLE
    watchlist_count = len(watchlist) if watchlist else 0

    # ==========================================
    # HTML COMPLETO
    # ==========================================
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

.header{{background:linear-gradient(135deg,#161b22 0%,#1a2332 100%);border-bottom:1px solid #30363d;padding:20px 30px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}}
.header-left{{display:flex;align-items:center;gap:15px}}
.logo{{font-size:28px;font-weight:700;color:#f0f6fc;letter-spacing:-0.5px}}
.logo span{{color:#58a6ff}}
.header-badge{{background:#238636;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}}
.header-right{{display:flex;align-items:center;gap:15px;font-size:13px;color:#8b949e}}
.header-right .dot{{width:8px;height:8px;border-radius:50%;display:inline-block}}

.container{{max-width:1400px;margin:0 auto;padding:20px}}

.section-title{{font-size:18px;font-weight:600;color:#f0f6fc;margin:30px 0 15px;padding-bottom:8px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px}}
.section-title:first-child{{margin-top:0}}

/* Nav tabs */
.nav-tabs{{display:flex;gap:5px;margin-bottom:20px;border-bottom:1px solid #30363d;padding-bottom:0;flex-wrap:wrap}}
.nav-tab{{padding:10px 20px;background:transparent;border:none;color:#8b949e;font-size:14px;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s}}
.nav-tab:hover{{color:#c9d1d9}}
.nav-tab.active{{color:#58a6ff;border-bottom-color:#58a6ff}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}

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

.categories-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px;margin-bottom:25px}}
.category-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;transition:border-color 0.2s}}
.category-card:hover{{border-color:#58a6ff}}
.cat-card-header{{display:flex;align-items:center;gap:10px;padding:15px 18px;background:#1c2333;border-bottom:1px solid #30363d}}
.cat-icon{{font-size:22px}}
.cat-group-name{{font-weight:600;color:#f0f6fc;flex:1}}
.cat-group-total{{font-size:12px;color:#8b949e;background:#21262d;padding:3px 10px;border-radius:10px}}
.cat-sub-list{{padding:10px 18px}}
.cat-sub-item{{display:flex;align-items:center;padding:10px;border-bottom:1px solid #21262d;transition:background 0.2s;user-select:none;cursor:pointer;border-radius:4px}}
.cat-sub-item:last-of-type{{border-bottom:none}}
.cat-sub-item:hover{{background:#1c2128}}
.cat-sub-toggle{{display:inline-block;width:16px;text-align:center;color:#8b949e;font-size:12px;transition:transform 0.3s ease;margin-right:8px}}
.cat-sub-item.expanded .cat-sub-toggle{{transform:rotate(90deg)}}
.cat-sub-name{{flex:1;color:#c9d1d9;font-size:13px}}
.cat-sub-meta{{display:flex;align-items:center;gap:8px;font-size:12px;color:#8b949e}}
.priority-badge{{display:inline-block;width:22px;height:22px;border-radius:50%;text-align:center;line-height:22px;font-size:11px;font-weight:700;color:#0d1117}}
.cat-sub-details{{background:#1c2128;border-left:3px solid #58a6ff;padding:15px;margin-top:5px;border-radius:6px;max-height:0;overflow:hidden;transition:max-height 0.3s ease,display 0.3s ease;display:none}}
.cat-sub-details.expanded{{max-height:3000px!important;display:block!important}}

.platform-badge{{display:inline-block;background:#21262d;color:#58a6ff;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600;border:1px solid #30363d}}
.no-items-box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:30px;text-align:center}}

.platforms-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:15px;margin-bottom:25px}}
.platform-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;transition:border-color 0.2s}}
.platform-card:hover{{border-color:#58a6ff}}
.plat-header{{display:flex;align-items:center;gap:15px;padding:18px;background:#1c2333;border-bottom:1px solid #30363d}}
.plat-icon{{font-size:32px}}
.plat-info{{flex:1}}
.plat-name{{font-weight:700;color:#f0f6fc;font-size:16px;margin-bottom:3px}}
.plat-desc{{font-size:12px;color:#8b949e;line-height:1.4}}
.plat-visit{{background:#238636;color:#fff;padding:6px 16px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;transition:background 0.2s;white-space:nowrap}}
.plat-visit:hover{{background:#2ea043;text-decoration:none}}
.plat-search{{display:flex;gap:8px;padding:12px 18px;align-items:center}}
.plat-input{{flex:1;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:8px 12px;border-radius:6px;font-size:13px;outline:none;transition:border-color 0.2s}}
.plat-input:focus{{border-color:#58a6ff}}
.plat-input:disabled{{opacity:0.5;cursor:not-allowed}}
.plat-btn{{background:#21262d;color:#58a6ff;border:1px solid #30363d;padding:8px 16px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all 0.2s;text-decoration:none;text-align:center;white-space:nowrap}}
.plat-btn:hover{{background:#30363d;border-color:#58a6ff;text-decoration:none}}

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

.finance-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px;margin-bottom:25px}}
.fin-card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px;text-align:center}}
.fin-card .fin-icon{{font-size:28px;margin-bottom:8px}}
.fin-card .fin-label{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px}}
.fin-card .fin-value{{font-size:24px;font-weight:700;margin-top:5px}}

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

/* Price history bars */
.price-bar-row{{display:flex;align-items:center;gap:10px;padding:8px 15px;border-bottom:1px solid #21262d}}
.price-bar-row:last-child{{border-bottom:none}}
.price-bar-row:hover{{background:#1c2128}}
.price-bar-label{{width:180px;font-size:12px;color:#c9d1d9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.price-bar-container{{flex:1;background:#21262d;border-radius:4px;height:16px;overflow:hidden}}
.price-bar-fill{{height:100%;background:linear-gradient(90deg,#238636,#3fb950);border-radius:4px;transition:width 0.5s ease}}
.price-bar-value{{width:80px;text-align:right;font-size:13px;font-weight:600;color:#3fb950}}
.price-bar-count{{width:40px;text-align:center;font-size:11px;color:#8b949e}}
.price-bar-range{{width:120px;text-align:right;font-size:11px;color:#8b949e}}

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

.footer{{text-align:center;padding:20px;color:#484f58;font-size:12px;border-top:1px solid #21262d;margin-top:20px}}

::-webkit-scrollbar{{width:8px}}
::-webkit-scrollbar-track{{background:#0d1117}}
::-webkit-scrollbar-thumb{{background:#30363d;border-radius:4px}}
::-webkit-scrollbar-thumb:hover{{background:#484f58}}

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
    .nav-tabs{{overflow-x:auto}}
    .price-bar-label{{width:100px}}
    .price-bar-range{{display:none}}
}}
@media(max-width:480px){{
    .overview-grid{{grid-template-columns:1fr}}
    .finance-grid{{grid-template-columns:1fr}}
    .term-list{{grid-template-columns:1fr}}
}}

/* SPINNER LOADING STYLES */
.loading-overlay {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
}}

.spinner-container {{
    text-align: center;
}}

.spinner {{
    width: 60px;
    height: 60px;
    border: 4px solid rgba(88, 166, 255, 0.2);
    border-top: 4px solid #58a6ff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
}}

@keyframes spin {{
    0% {{ transform: rotate(0deg); }}
    100% {{ transform: rotate(360deg); }}
}}

.spinner-container p {{
    color: #c9d1d9;
    font-size: 18px;
    font-weight: 600;
    margin: 0;
    animation: pulse 1.5s ease-in-out infinite;
}}

@keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.6; }}
}}
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <div class="logo">Agente de Leiloes <span>R33</span></div>
        <span class="header-badge">Painel de Controle v5.0</span>
    </div>
    <div class="header-right">
        <span class="dot" style="background:{status_color}"></span>
        <span>{agent_status}</span>
        <span>|</span>
        <span>Atualizado: {now.strftime("%d/%m/%Y %H:%M:%S")}</span>
        <span>|</span>
        <span>Auto-refresh: 60s</span>
        <span>|</span>
        <button onclick="scanNow(event)" style="background:#238636;color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;transition:background 0.2s;margin-right:8px" onmouseover="this.style.background='#2ea043'" onmouseout="this.style.background='#238636'">Varredura Manual</button>
        <button onclick="clearAllData(event)" style="background:#f85149;color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;transition:background 0.2s" onmouseover="this.style.background='#da3633'" onmouseout="this.style.background='#f85149'">Limpar Dados</button>
    </div>
</div>

<div class="container">

    <!-- SPINNER OVERLAY -->
    <div id="loadingSpinner" class="loading-overlay" style="display:none;">
        <div class="spinner-container">
            <div class="spinner"></div>
            <p>Fazendo busca, aguarde...</p>
        </div>
    </div>

    <!-- NAVIGATION TABS -->
    <div class="nav-tabs">
        <button class="nav-tab active" onclick="switchTab('overview')">Visao Geral</button>
        <button class="nav-tab" onclick="switchTab('agenda')">Agenda ({watchlist_count})</button>
        <button class="nav-tab" onclick="switchTab('categories')">Categorias</button>
        <button class="nav-tab" onclick="switchTab('auctions')">Leiloes Encontrados</button>
        <button class="nav-tab" onclick="switchTab('history')">Historico de Precos</button>
        <button class="nav-tab" onclick="switchTab('financial')">Financeiro</button>
        <button class="nav-tab" onclick="switchTab('logs')">Logs</button>
        <button class="nav-tab" onclick="switchTab('platforms')">Plataformas</button>
    </div>

    <!-- TAB: VISAO GERAL -->
    <div id="tab-overview" class="tab-content active">
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
                <div class="ov-label">Na Agenda</div>
                <div class="ov-value orange">{watchlist_count}</div>
                <div class="ov-sub">Leiloes monitorados</div>
            </div>
            <div class="overview-card">
                <div class="ov-label">Alertas Enviados</div>
                <div class="ov-value orange">{counters["alerts_sent"]}</div>
                <div class="ov-sub">Via Telegram</div>
            </div>
        </div>

        <!-- Quick summary of watchlist -->
        <div class="section-title">Agenda Rapida</div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>ID</th><th>Titulo</th><th>Site</th><th>Preco Atual</th><th>Teto</th><th>Progresso</th><th>Encerra</th><th>Acao</th></tr>
                </thead>
                <tbody>{watchlist_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- TAB: AGENDA -->
    <div id="tab-agenda" class="tab-content">
        <div class="section-title">Agenda de Leiloes Monitorados</div>
        <div class="overview-grid" style="margin-bottom:20px">
            <div class="overview-card">
                <div class="ov-label">Monitorando</div>
                <div class="ov-value blue">{watchlist_count}</div>
                <div class="ov-sub">Leiloes ativos na agenda</div>
            </div>
            <div class="overview-card">
                <div class="ov-label">Verificacao de Preco</div>
                <div class="ov-value">30 min</div>
                <div class="ov-sub">Intervalo de monitoramento</div>
            </div>
            <div class="overview-card">
                <div class="ov-label">Lembretes</div>
                <div class="ov-value green">Ativo</div>
                <div class="ov-sub">24h, 1h, 15min antes</div>
            </div>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>ID</th><th>Titulo</th><th>Site</th><th>Preco Atual</th><th>Teto</th><th>Progresso</th><th>Encerra</th><th>Acao</th></tr>
                </thead>
                <tbody>{watchlist_rows}</tbody>
            </table>
        </div>
        <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-top:15px">
            <div style="color:#f0f6fc;font-weight:600;margin-bottom:10px">Como usar a Agenda</div>
            <div style="font-size:13px;color:#8b949e;line-height:1.8">
                <strong style="color:#58a6ff">/agendar URL TETO</strong> - Adiciona um leilao a agenda<br>
                <strong style="color:#58a6ff">/agenda</strong> - Lista todos os leiloes monitorados<br>
                <strong style="color:#58a6ff">/teto ID VALOR</strong> - Altera o teto de um leilao<br>
                <strong style="color:#58a6ff">/cancelar ID</strong> - Remove um leilao da agenda<br>
                <strong style="color:#58a6ff">/arquivar ID</strong> - Move para o arquivo<br>
            </div>
        </div>
    </div>

    <!-- TAB: CATEGORIAS -->
    <div id="tab-categories" class="tab-content">
        <div class="section-title">Categorias de Busca ({total_categories} categorias, {total_terms} termos)</div>
        <div class="categories-grid">{cat_cards_html}</div>
    </div>

    <!-- TAB: LEILOES ENCONTRADOS -->
    <div id="tab-auctions" class="tab-content">
        <div class="section-title">Ultimos Leiloes Encontrados</div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr><th>Titulo</th><th>Site</th><th>Preco</th><th>Status</th><th>Acao</th></tr>
                </thead>
                <tbody>{items_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- TAB: HISTORICO DE PRECOS -->
    <div id="tab-history" class="tab-content">
        <div class="section-title">Historico de Precos por Categoria</div>
        <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;margin-bottom:25px">
            <div style="display:flex;align-items:center;padding:12px 15px;background:#1c2333;border-bottom:1px solid #30363d;font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px">
                <div style="width:180px">Categoria</div>
                <div style="flex:1">Preco Medio</div>
                <div style="width:80px;text-align:right">Media</div>
                <div style="width:40px;text-align:center">Qtd</div>
                <div style="width:120px;text-align:right">Faixa</div>
            </div>
            {price_bars_html}
        </div>
        <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-top:15px">
            <div style="color:#f0f6fc;font-weight:600;margin-bottom:10px">Consultar Historico</div>
            <div style="font-size:13px;color:#8b949e;line-height:1.8">
                <strong style="color:#58a6ff">/historico PRODUTO</strong> - Mostra historico de precos de um produto<br>
                <strong style="color:#58a6ff">/preco PRODUTO</strong> - Mostra preco medio de arrematacao<br>
            </div>
        </div>
    </div>

    <!-- TAB: FINANCEIRO -->
    <div id="tab-financial" class="tab-content">
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
    </div>

    <!-- TAB: LOGS -->
    <div id="tab-logs" class="tab-content">
        <div class="section-title">Logs Recentes dos Scrapers</div>
        <div class="logs-container">{logs_html}</div>
    </div>

    <!-- TAB: PLATAFORMAS -->
    <div id="tab-platforms" class="tab-content">
        <div class="section-title">Plataformas de Leilao</div>
        <div class="platforms-grid">

            <div class="platform-card">
                <div class="plat-header" style="border-left:4px solid #3fb950">
                    <div class="plat-icon">&#127981;</div>
                    <div class="plat-info">
                        <div class="plat-name">GovDeals</div>
                        <div class="plat-desc">Leiloes de equipamentos governamentais e excedentes publicos</div>
                    </div>
                    <a href="https://www.govdeals.com" target="_blank" class="plat-visit">Visitar</a>
                </div>
                <div class="plat-search">
                    <input type="text" id="search-govdeals" placeholder="Buscar em GovDeals..." class="plat-input" onkeydown="if(event.key==='Enter')searchPlatform('govdeals')">
                    <button onclick="searchPlatform('govdeals')" class="plat-btn">Buscar</button>
                </div>
            </div>

            <div class="platform-card">
                <div class="plat-header" style="border-left:4px solid #58a6ff">
                    <div class="plat-icon">&#128296;</div>
                    <div class="plat-info">
                        <div class="plat-name">BidSpotter</div>
                        <div class="plat-desc">Leiloes industriais e de equipamentos comerciais</div>
                    </div>
                    <a href="https://www.bidspotter.com" target="_blank" class="plat-visit">Visitar</a>
                </div>
                <div class="plat-search">
                    <input type="text" id="search-bidspotter" placeholder="Buscar em BidSpotter..." class="plat-input" onkeydown="if(event.key==='Enter')searchPlatform('bidspotter')">
                    <button onclick="searchPlatform('bidspotter')" class="plat-btn">Buscar</button>
                </div>
            </div>

            <div class="platform-card">
                <div class="plat-header" style="border-left:4px solid #d2a8ff">
                    <div class="plat-icon">&#127970;</div>
                    <div class="plat-info">
                        <div class="plat-name">Public Surplus</div>
                        <div class="plat-desc">Excedentes de agencias publicas e municipios</div>
                    </div>
                    <a href="https://www.publicsurplus.com" target="_blank" class="plat-visit">Visitar</a>
                </div>
                <div class="plat-search">
                    <input type="text" id="search-publicsurplus" placeholder="Buscar em Public Surplus..." class="plat-input" onkeydown="if(event.key==='Enter')searchPlatform('publicsurplus')">
                    <button onclick="searchPlatform('publicsurplus')" class="plat-btn">Buscar</button>
                </div>
            </div>

            <div class="platform-card">
                <div class="plat-header" style="border-left:4px solid #f0883e">
                    <div class="plat-icon">&#128666;</div>
                    <div class="plat-info">
                        <div class="plat-name">JJ Kane</div>
                        <div class="plat-desc">Leiloes de veiculos, equipamentos pesados e golf carts</div>
                    </div>
                    <a href="https://www.jjkane.com" target="_blank" class="plat-visit">Visitar</a>
                </div>
                <div class="plat-search">
                    <input type="text" id="search-jjkane" placeholder="Buscar em JJ Kane..." class="plat-input" onkeydown="if(event.key==='Enter')searchPlatform('jjkane')">
                    <button onclick="searchPlatform('jjkane')" class="plat-btn">Buscar</button>
                </div>
            </div>

            <div class="platform-card">
                <div class="plat-header" style="border-left:4px solid #f85149">
                    <div class="plat-icon">&#127908;</div>
                    <div class="plat-info">
                        <div class="plat-name">AVGear</div>
                        <div class="plat-desc">Leiloes especiais de equipamentos de audio e video profissional</div>
                    </div>
                    <a href="https://www.avgear.com/pages/auctions" target="_blank" class="plat-visit">Visitar</a>
                </div>
                <div class="plat-search">
                    <input type="text" id="search-avgear" placeholder="AVGear nao tem busca (leiloes via parceiros)" class="plat-input" disabled>
                    <a href="https://www.avgear.com/pages/auctions" target="_blank" class="plat-btn">Ver Leiloes</a>
                </div>
            </div>

        </div>
    </div>

</div>

<div class="footer">
    Agente de Leiloes R33 v5.0 &mdash; Gestao Completa &mdash;
    {total_terms} termos em {total_categories} categorias &mdash;
    {watchlist_count} leiloes na agenda &mdash;
    Render Free (512MB RAM) &mdash;
    {now.strftime("%d/%m/%Y %H:%M:%S")}
</div>

<script>
window.categoryDataCache = {{}};

function searchPlatform(platform) {{
    var urls = {{
        'govdeals': 'https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg=Classic&kword=',
        'bidspotter': 'https://www.bidspotter.com/en-us/search?query=',
        'publicsurplus': 'https://www.publicsurplus.com/sms/browse/search?posting=y&keyword=',
        'jjkane': 'https://www.jjkane.com/search?q='
    }};
    var input = document.getElementById('search-' + platform);
    if (!input || !input.value.trim()) {{
        alert('Digite um termo de busca');
        return;
    }}
    var term = encodeURIComponent(input.value.trim());
    var url = urls[platform];
    if (url) {{
        window.open(url + term, '_blank');
    }}
}}

function clearAllData(event) {{
    if (!confirm('Tem certeza que deseja limpar TODOS os dados? Esta acao nao pode ser desfeita!')) {{
        return;
    }}
    
    var btn = event.currentTarget || event.target;
    if (!btn) {{
        alert('Erro: botao nao encontrado');
        return;
    }}
    btn.disabled = true;
    btn.textContent = 'Limpando...';
    
    console.log('Iniciando limpeza de dados...');
    
    fetch('/api/clear-data', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}}
    }})
    .then(function(response) {{
        console.log('Resposta HTTP:', response.status);
        if (!response.ok) {{
            throw new Error('HTTP ' + response.status + ': ' + response.statusText);
        }}
        return response.json();
    }})
    .then(function(data) {{
        console.log('Dados retornados:', data);
        if (data.status === 'success') {{
            alert('Dados limpos com sucesso! O dashboard sera atualizado em 3 segundos...');
            window.categoryDataCache = {{}};
            setTimeout(function() {{
                location.reload();
            }}, 3000);
        }} else {{
            alert('Erro: ' + data.message);
            btn.disabled = false;
            btn.textContent = 'Limpar Dados';
        }}
    }})
    .catch(function(error) {{
        console.error('Erro na requisicao:', error);
        alert('Erro ao limpar dados: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Limpar Dados';
    }});
}}

function scanNow(event) {{
    var btn = event.currentTarget || event.target;
    if (!btn) {{
        alert('Erro: botao nao encontrado');
        return;
    }}
    btn.disabled = true;
    btn.textContent = 'Buscando...';
    
    // Mostrar spinner
    var spinner = document.getElementById('loadingSpinner');
    if (spinner) {{
        spinner.style.display = 'flex';
    }}
    
    console.log('Iniciando varredura manual...');
    
    // Timeout de 90 segundos para esconder o spinner (caso a busca demore)
    var timeoutId = setTimeout(function() {{
        if (spinner) {{
            spinner.style.display = 'none';
        }}
        btn.disabled = false;
        btn.textContent = 'Varredura Manual';
        alert('Varredura concluida! Recarregando dashboard...');
        location.reload();
    }}, 90000);
    
    fetch('/api/scan-now', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}}
    }})
    .then(function(response) {{
        console.log('Resposta HTTP:', response.status);
        if (!response.ok) {{
            throw new Error('HTTP ' + response.status + ': ' + response.statusText);
        }}
        return response.json();
    }})
    .then(function(data) {{
        console.log('Dados retornados:', data);
        clearTimeout(timeoutId);
        if (data.status === 'success') {{
            // Esconder spinner
            if (spinner) {{
                spinner.style.display = 'none';
            }}
            btn.disabled = false;
            btn.textContent = 'Varredura Manual';
            // Recarrega o dashboard em 5 segundos para mostrar novos resultados
            setTimeout(function() {{
                location.reload();
            }}, 5000);
        }} else {{
            if (spinner) {{
                spinner.style.display = 'none';
            }}
            alert('Erro: ' + data.message);
            btn.disabled = false;
            btn.textContent = 'Varredura Manual';
        }}
    }})
    .catch(function(error) {{
        console.error('Erro na requisicao:', error);
        clearTimeout(timeoutId);
        if (spinner) {{
            spinner.style.display = 'none';
        }}
        alert('Erro ao iniciar varredura: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Varredura Manual';
    }});
}}

function switchTab(tabName) {{
    document.querySelectorAll('.tab-content').forEach(function(el) {{
        el.classList.remove('active');
    }});
    document.querySelectorAll('.nav-tab').forEach(function(el) {{
        el.classList.remove('active');
    }});
    var tab = document.getElementById('tab-' + tabName);
    if (tab) tab.classList.add('active');
    if (event && event.target) event.target.classList.add('active');
}}

function toggleCategory(elem, event) {{
    if (event) event.stopPropagation();
    
    var categoryName = elem.getAttribute('data-category');
    if (!categoryName) {{
        console.error('data-category nao encontrado');
        return;
    }}
    
    var detailsId = 'details-' + categoryName.replace(/ /g, '_').replace(/\//g, '_').toLowerCase();
    var detailsElem = document.getElementById(detailsId);
    
    if (!detailsElem) {{
        console.error('Elemento detalhes nao encontrado:', detailsId);
        return;
    }}
    
    var isExpanded = elem.classList.contains('expanded');
    console.log('Toggle category:', categoryName, 'expanded:', isExpanded);
    
    if (isExpanded) {{
        elem.classList.remove('expanded');
        detailsElem.classList.remove('expanded');
        detailsElem.style.maxHeight = '0px';
        detailsElem.style.display = 'none';
    }} else {{
        elem.classList.add('expanded');
        detailsElem.classList.add('expanded');
        detailsElem.style.display = 'block';
        
        if (detailsElem.querySelector('.loading')) {{
            loadCategoryData(categoryName, detailsElem);
        }}
        
        setTimeout(function() {{
            detailsElem.style.maxHeight = '3000px';
        }}, 10);
    }}
}}

function loadCategoryData(categoryName, detailsElem) {{
    console.log('Carregando dados para:', categoryName);
    
    if (window.categoryDataCache[categoryName]) {{
        console.log('Usando cache para:', categoryName);
        renderCategoryData(window.categoryDataCache[categoryName], detailsElem);
        return;
    }}
    
    fetch('/api/category/' + encodeURIComponent(categoryName))
        .then(function(response) {{
            console.log('Response status:', response.status);
            return response.json();
        }})
        .then(function(data) {{
            console.log('Dados recebidos:', data);
            window.categoryDataCache[categoryName] = data;
            renderCategoryData(data, detailsElem);
        }})
        .catch(function(error) {{
            console.error('Erro ao carregar categoria:', error);
            detailsElem.innerHTML = '<div class="no-items">Erro ao carregar: ' + error.message + '</div>';
        }});
}}

function renderCategoryData(data, detailsElem) {{
    if (data.error) {{
        detailsElem.innerHTML = '<div class="no-items">Erro: ' + data.error + '</div>';
        return;
    }}
    
    var html = '';
    
    /* Contar total de produtos encontrados */
    var totalItems = 0;
    for (var t in data.items_by_term) {{
        if (data.items_by_term.hasOwnProperty(t)) {{
            totalItems += data.items_by_term[t].length;
        }}
    }}
    
    if (totalItems > 0) {{
        /* Mostrar tabela de produtos encontrados */
        html += '<table class="items-table"><thead><tr>';
        html += '<th>Produto</th><th>Termo</th><th>Plataforma</th><th>Preco</th><th>Acao</th>';
        html += '</tr></thead><tbody>';
        
        for (var term in data.items_by_term) {{
            if (data.items_by_term.hasOwnProperty(term) && data.items_by_term[term].length > 0) {{
                data.items_by_term[term].forEach(function(item) {{
                    var title = item.title || item.name || 'N/A';
                    var price = item.price || 'N/A';
                    var site = item.site || 'N/A';
                    var link = item.link || item.url || '#';
                    html += '<tr>';
                    html += '<td class="item-title" title="' + title + '">' + title + '</td>';
                    html += '<td style="color:#8b949e;font-size:11px">' + term + '</td>';
                    html += '<td><span class="platform-badge">' + site + '</span></td>';
                    html += '<td class="item-price">' + price + '</td>';
                    html += '<td><a href="' + link + '" target="_blank" class="item-link">Ver Leilao</a></td>';
                    html += '</tr>';
                }});
            }}
        }}
        
        html += '</tbody></table>';
    }} else {{
        /* Quando nao ha produtos, mostrar apenas texto discreto */
        html += '<div style="color:#8b949e;font-size:12px;padding:10px 0">Aguardando resultados...</div>';
    }}
    
    detailsElem.innerHTML = html;
}}
</script>

</body>
</html>"""
    return html


@app.route("/dashboard")
def dashboard():
    html = _build_dashboard_html()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ==========================================
# INICIALIZACAO
# ==========================================
def start_agent():
    global agent
    try:
        setup_webhook()
        agent = AuctionAgent()
        agent.start()
    except Exception as e:
        logger.critical(f"Erro fatal ao iniciar o agente: {e}")


if __name__ == "__main__":
    agent_thread = threading.Thread(target=start_agent, daemon=True)
    agent_thread.start()
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Iniciando servidor Flask na porta {port}...")
    app.run(host="0.0.0.0", port=port)
