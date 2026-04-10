import time
import logging
import sys
import os
from datetime import datetime

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "agent.log")),
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

class AuctionAgent:
    """Agente principal que coordena todos os módulos."""
    
    def __init__(self):
        logger.info("Inicializando Agente de Leilões...")
        
        # Inicializa banco de dados
        database.init_db()
        
        # Inicializa módulos
        self.bot = AuctionTelegramBot()
        self.analyzer = AuctionAnalyzer()
        self.agenda = AgendaManager(self.bot)
        self.post_auction = PostAuctionManager(self.bot)
        
        # Inicializa scrapers
        self.scrapers = [
            GovDealsScraper(),
            PublicSurplusScraper(),
            BidSpotterScraper(),
            AVGearScraper(),
            JJKaneScraper()
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
        
        # Loop principal de monitoramento
        self._monitoring_loop()
        
    def _monitoring_loop(self):
        """Loop principal que executa os scrapers periodicamente."""
        logger.info(f"Iniciando loop de monitoramento (intervalo: {config.CHECK_INTERVAL}s)")
        
        while True:
            try:
                self._run_scrapers()
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")
                
            logger.info(f"Aguardando {config.CHECK_INTERVAL} segundos para a próxima verificação...")
            time.sleep(config.CHECK_INTERVAL)
            
    def _run_scrapers(self):
        """Executa todos os scrapers para todas as palavras-chave."""
        logger.info("Iniciando nova rodada de scraping...")
        
        for keyword in config.KEYWORDS:
            for scraper in self.scrapers:
                try:
                    # Busca itens
                    items = scraper.search(keyword)
                    
                    # Processa cada item encontrado
                    for item in items:
                        self._process_item(item)
                        
                except Exception as e:
                    logger.error(f"Erro ao executar scraper {scraper.site_name} para '{keyword}': {e}")
                    
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

if __name__ == "__main__":
    try:
        agent = AuctionAgent()
        agent.start()
    except KeyboardInterrupt:
        logger.info("Agente encerrado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal no agente: {e}")
