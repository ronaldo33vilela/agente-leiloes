from .base_scraper import BaseScraper, logger
import re
import json

class BidSpotterScraper(BaseScraper):
    """
    Scraper para o site BidSpotter.
    BidSpotter usa JavaScript pesado para renderizar os resultados.
    Tentamos usar a API interna ou Selenium como fallback.
    """
    
    def __init__(self):
        super().__init__("BidSpotter")
        self.base_url = "https://www.bidspotter.com"
        self.driver = None
        
    def _init_driver(self):
        """Inicializa o Selenium WebDriver se ainda não estiver ativo."""
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
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("Selenium WebDriver inicializado para BidSpotter.")
        except Exception as e:
            logger.error(f"Erro ao inicializar Selenium para BidSpotter: {e}")
            self.driver = None
        
    def search(self, keyword):
        """Busca itens no BidSpotter."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        self._init_driver()
        if not self.driver:
            logger.warning("Selenium não disponível para BidSpotter. Tentando fallback...")
            return self._search_fallback(keyword)
            
        try:
            import time
            
            # Navega para a página principal e usa o campo de busca
            search_url = f"{self.base_url}/en-us"
            self.driver.get(search_url)
            time.sleep(3)
            
            # Encontra o campo de busca e insere a keyword
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            
            search_input = self.driver.find_element(By.ID, 'searchTerm')
            search_input.clear()
            search_input.send_keys(keyword)
            search_input.send_keys(Keys.RETURN)
            
            time.sleep(5)
            
            # Extrai os resultados
            results = []
            
            # Tenta encontrar os cards de resultado
            cards = self.driver.find_elements(By.CSS_SELECTOR, '.lot-card, .search-result, [class*="lot"]')
            
            for card in cards[:20]:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, 'a, h3, h4, .title')
                    title = title_elem.text.strip()
                    link = title_elem.get_attribute('href') or ''
                    
                    # Tenta encontrar o preço
                    price_text = "Preço não encontrado"
                    try:
                        price_elem = card.find_element(By.CSS_SELECTOR, '.price, [class*="price"], [class*="bid"]')
                        price_text = price_elem.text.strip()
                    except:
                        pass
                    
                    if title and link:
                        item_id = f"bidspotter_{hash(link) % 100000}"
                        results.append({
                            "id": item_id,
                            "site": self.site_name,
                            "title": title,
                            "link": link,
                            "price": price_text,
                            "keyword": keyword
                        })
                except:
                    continue
                    
            logger.info(f"Encontrados {len(results)} itens no {self.site_name} para '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Erro no Selenium para {self.site_name}: {e}")
            return self._search_fallback(keyword)
            
    def _search_fallback(self, keyword):
        """Fallback usando requests."""
        logger.info(f"Usando fallback para {self.site_name}...")
        
        # Tenta buscar via URL direta
        search_url = f"{self.base_url}/en-us/search"
        params = {"query": keyword}
        
        soup = self.fetch_page(search_url, params=params)
        if not soup:
            return []
            
        results = []
        links = soup.find_all('a', href=re.compile(r'/auction-catalogues/.*lot-details'))
        
        processed = set()
        for link_elem in links:
            try:
                href = link_elem.get('href', '')
                if href in processed:
                    continue
                processed.add(href)
                
                title = link_elem.text.strip() or link_elem.get('title', '')
                if not title:
                    continue
                    
                item_id = f"bidspotter_{hash(href) % 100000}"
                results.append({
                    "id": item_id,
                    "site": self.site_name,
                    "title": title,
                    "link": f"{self.base_url}{href}" if not href.startswith('http') else href,
                    "price": "Preço não encontrado",
                    "keyword": keyword
                })
            except:
                continue
                
        logger.info(f"Fallback encontrou {len(results)} itens no {self.site_name}")
        return results
        
    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
