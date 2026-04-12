import time
import logging
import sys
import os
import gc
import json
import threading
import re
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


class SearchRotator:
    """Gerencia a rotação de termos de busca entre ciclos.

    A cada ciclo (1 hora), seleciona um subconjunto de termos respeitando
    a ordem de prioridade (A → B → C) e rotaciona para o próximo bloco
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
            logger.warning(f"Não foi possível salvar estado de rotação: {e}")

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
            f"(próximo offset={self._offset})"
        )
        return batch


class AuctionAgent:
    """Agente principal que coordena todos os módulos.
    Otimizado para Render Free (512MB RAM) — sem Selenium.
    """

    def __init__(self):
        logger.info("Inicializando Agente de Leilões (modo leve — sem Selenium)...")

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
        logger.info("Iniciando serviços do agente...")

        # Inicia o bot do Telegram
        self.bot.start_polling()

        # Inicia o gerenciador de agenda
        self.agenda.start()

        # Inicia o gerenciador de pós-arrematação
        self.post_auction.start()

        # Inicia loop de monitoramento em thread separada
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()

        logger.info("Todos os serviços iniciados com sucesso.")

    def _monitoring_loop(self):
        """Loop principal que executa os scrapers periodicamente."""
        logger.info(f"Iniciando loop de monitoramento (intervalo: {config.CHECK_INTERVAL}s)")

        while True:
            try:
                self._run_scrapers()
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")

            # Força coleta de lixo após cada rodada
            gc.collect()

            logger.info(f"Aguardando {config.CHECK_INTERVAL} segundos para a próxima verificação...")
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
                finally:
                    # Libera o scraper da memória
                    if scraper:
                        scraper.session.close()
                        del scraper
                    gc.collect()

                # Delay entre requisições para evitar bloqueio
                time.sleep(config.REQUEST_DELAY)

        logger.info(f"Rodada concluída: {total_found} itens encontrados no total.")

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
                    f"Item ignorado (preço ${numeric_price:,.0f} > máx ${max_price:,} "
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
        if analysis.get("recommendation") in ["ÓTIMA OPORTUNIDADE", "BOA OPORTUNIDADE"]:
            self.bot.send_alert(item, analysis)

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
        "service": "Agente de Leilões Americanos",
        "version": "3.0-categories",
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
# INICIALIZAÇÃO
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
