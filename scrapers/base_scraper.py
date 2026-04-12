import requests
from bs4 import BeautifulSoup
import logging
import sys
import os
import gc

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
    """Classe base para todos os scrapers de leilão.
    Otimizada para baixo consumo de memória (Render Free 512MB).
    Usa apenas requests + BeautifulSoup, sem Selenium.
    """
    
    def __init__(self, site_name):
        self.site_name = site_name
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        
    def fetch_page(self, url, params=None, verify=True):
        """Faz a requisição HTTP e retorna o objeto BeautifulSoup."""
        try:
            response = self.session.get(url, params=params, timeout=10, verify=verify)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # Libera o texto bruto da resposta para economizar memória
            del response
            gc.collect()
            return soup
        except requests.RequestException as e:
            logger.error(f"Erro ao acessar {url}: {e}")
            return None

    def fetch_json(self, url, params=None, verify=True):
        """Faz a requisição HTTP e retorna o JSON da resposta."""
        try:
            response = self.session.get(url, params=params, timeout=10, verify=verify)
            response.raise_for_status()
            data = response.json()
            del response
            gc.collect()
            return data
        except requests.RequestException as e:
            logger.error(f"Erro ao acessar JSON {url}: {e}")
            return None
        except ValueError as e:
            logger.error(f"Erro ao decodificar JSON de {url}: {e}")
            return None
            
    def search(self, keyword):
        """Método a ser implementado pelas subclasses."""
        raise NotImplementedError("Subclasses devem implementar o método search()")
