import time
import logging
import sys
import os
import gc
import threading
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

class AuctionAgent:
    """Agente principal que coordena todos os módulos.
    Otimizado para Render Free (512MB RAM) - sem Selenium.
    """
    
    def __init__(self):
        logger.info("Inicializando Agente de Leilões (modo leve - sem Selenium)...")
        
        # Inicializa banco de dados
        database.init_db()
        
        # Inicializa módulos
        self.bot = AuctionTelegramBot()
        self.analyzer = AuctionAnalyzer()
        self.agenda = AgendaManager(self.bot)
        self.post_auction = PostAuctionManager(self.bot)
        
        # Scrapers são instanciados sob demanda para economizar memória
        self._scraper_classes = [
            GovDealsScraper,
            PublicSurplusScraper,
            BidSpotterScraper,
            AVGearScraper,
            JJKaneScraper
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
        """Executa todos os scrapers para todas as palavras-chave.
        Instancia e destrói cada scraper individualmente para economizar memória.
        """
        logger.info("Iniciando nova rodada de scraping...")
        
        for keyword in config.KEYWORDS:
            for scraper_class in self._scraper_classes:
                scraper = None
                try:
                    # Instancia o scraper sob demanda
                    scraper = scraper_class()
                    
                    # Busca itens
                    items = scraper.search(keyword)
                    
                    # Processa cada item encontrado
                    for item in items:
                        self._process_item(item)
                        
                except Exception as e:
                    site_name = scraper.site_name if scraper else scraper_class.__name__
                    logger.error(f"Erro ao executar scraper {site_name} para '{keyword}': {e}")
                finally:
                    # Libera o scraper da memória
                    if scraper:
                        scraper.session.close()
                        del scraper
                    gc.collect()
                    
    def _process_item(self, item):
        """Processa um item encontrado, analisa e envia alerta se necessário."""
        item_id = item['id']
        
        # Verifica se já foi notificado
        if database.is_item_notified(item_id):
            return
            
        logger.info(f"Novo item encontrado: {item['title']} ({item['site']})")
        
        # Analisa o item com LLM
        analysis = self.analyzer.analyze_item(
            title=item['title'],
            price=item['price'],
            site=item['site'],
            keyword=item['keyword']
        )
        
        # Se a recomendação for boa, envia alerta
        if analysis.get('recommendation') in ["ÓTIMA OPORTUNIDADE", "BOA OPORTUNIDADE"]:
            self.bot.send_alert(item, analysis)
            
        # Marca como notificado para não enviar novamente
        database.mark_item_notified(
            item_id=item_id,
            site=item['site'],
            title=item['title'],
            link=item['link'],
            price=item['price']
        )

# ==========================================
# ROTAS FLASK (para manter o Render ativo)
# ==========================================
agent = None

@app.route('/')
def home():
    """Rota principal - health check."""
    return jsonify({
        "status": "running",
        "service": "Agente de Leilões Americanos",
        "version": "2.0-lite",
        "memory_mode": "optimized (no Selenium)",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Health check para o Render."""
    return jsonify({"status": "healthy"}), 200

@app.route('/stats')
def stats():
    """Retorna estatísticas do agente."""
    try:
        stats_data = database.get_dashboard_stats()
        return jsonify({
            "status": "ok",
            "stats": stats_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
    app.run(host='0.0.0.0', port=port)
