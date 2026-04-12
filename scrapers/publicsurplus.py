from .base_scraper import BaseScraper, logger
import re
import urllib3
import ssl

# Desabilita avisos de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PublicSurplusScraper(BaseScraper):
    """
    Scraper para o site Public Surplus.
    O site pode ter problemas de SSL, então usamos configurações especiais.
    """
    
    def __init__(self):
        super().__init__("Public Surplus")
        self.base_url = "https://www.publicsurplus.com"
        self.driver = None
        
    def _init_driver(self):
        """Inicializa o Selenium WebDriver."""
        if self.driver:
            return
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("Selenium WebDriver inicializado para Public Surplus.")
        except Exception as e:
            logger.error(f"Erro ao inicializar Selenium para Public Surplus: {e}")
            self.driver = None
        
    def search(self, keyword):
        """Busca itens no Public Surplus."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Tenta primeiro com requests (mais rápido)
        results = self._search_requests(keyword)
        if results:
            return results
            
        # Fallback para Selenium
        return self._search_selenium(keyword)
        
    def _search_requests(self, keyword):
        """Busca usando requests com tratamento especial de SSL."""
        search_url = f"{self.base_url}/sms/browse/search"
        params = {
            "posting": "y",
            "keyword": keyword
        }
        
        try:
            # Tenta com verificação SSL desabilitada
            response = self.session.get(search_url, params=params, timeout=15, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao acessar {self.site_name}: {e}")
            return []
            
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        return self._parse_results(soup)
        
    def _search_selenium(self, keyword):
        """Busca usando Selenium (fallback para problemas de SSL)."""
        self._init_driver()
        if not self.driver:
            return []
            
        try:
            import time
            from selenium.webdriver.common.by import By
            
            search_url = f"{self.base_url}/sms/browse/search?posting=y&keyword={keyword.replace(' ', '+')}"
            self.driver.get(search_url)
            time.sleep(5)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            return self._parse_results(soup)
            
        except Exception as e:
            logger.error(f"Erro no Selenium para {self.site_name}: {e}")
            return []
        
    def _parse_results(self, soup):
        """Extrai resultados do HTML do Public Surplus."""
        results = []
        processed_ids = set()
        
        # Encontra os links de resultados
        links = soup.find_all('a', href=re.compile(r'/sms/auction/view\?auc='))
        
        for link_elem in links:
            try:
                href = link_elem['href']
                text = link_elem.text.strip()
                
                # Ignora links que são apenas "View Images" ou vazios
                if not text or "View Images" in text or len(text) < 5:
                    continue
                    
                # Extrai o ID do leilão
                match = re.search(r'auc=(\d+)', href)
                if not match:
                    continue
                    
                auction_id = match.group(1)
                item_id = f"publicsurplus_{auction_id}"
                
                if item_id in processed_ids:
                    continue
                processed_ids.add(item_id)
                
                # Título
                title = text
                title = re.sub(r'^#\d+\s*-\s*', '', title)
                
                # Preço - procura no contexto próximo (sobe até a row da tabela)
                price_text = "Consultar no site"
                parent = link_elem
                for _ in range(5):
                    parent = parent.parent
                    if parent is None:
                        break
                    price_match = re.search(r'\$[\d,]+\.?\d*', parent.text)
                    if price_match:
                        price_text = price_match.group(0)
                        break
                
                # Monta o link completo
                full_link = href if href.startswith('http') else f"{self.base_url}{href}"
                
                results.append({
                    "id": item_id,
                    "site": self.site_name,
                    "title": title,
                    "link": full_link,
                    "price": price_text,
                    "keyword": keyword
                })
                
            except Exception as e:
                logger.error(f"Erro ao processar item no {self.site_name}: {e}")
                
        logger.info(f"Encontrados {len(results)} itens no {self.site_name} para '{keyword}'")
        return results
        
    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
