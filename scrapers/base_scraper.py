import requests
from bs4 import BeautifulSoup
import logging
import sys
import os

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Scraper')

class BaseScraper:
    """Classe base para todos os scrapers de leilão."""
    
    def __init__(self, site_name):
        self.site_name = site_name
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        
    def fetch_page(self, url, params=None):
        """Faz a requisição HTTP e retorna o objeto BeautifulSoup."""
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Erro ao acessar {url}: {e}")
            return None
            
    def search(self, keyword):
        """Método a ser implementado pelas subclasses."""
        raise NotImplementedError("Subclasses devem implementar o método search()")
