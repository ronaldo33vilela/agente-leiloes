from .base_scraper import BaseScraper, logger
import re

class JJKaneScraper(BaseScraper):
    """
    Scraper para o site JJ Kane Auctions.
    JJ Kane usa Cloudflare e pode bloquear requests diretos.
    Usamos Selenium como método principal.
    """
    
    def __init__(self):
        super().__init__("JJ Kane")
        self.base_url = "https://www.jjkane.com"
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
            logger.info("Selenium WebDriver inicializado para JJ Kane.")
        except Exception as e:
            logger.error(f"Erro ao inicializar Selenium para JJ Kane: {e}")
            self.driver = None
        
    def search(self, keyword):
        """Busca itens no JJ Kane usando Selenium."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        self._init_driver()
        if not self.driver:
            return self._search_fallback(keyword)
            
        try:
            import time
            from selenium.webdriver.common.by import By
            
            # Tenta múltiplas URLs de busca
            urls_to_try = [
                f"{self.base_url}/search?q={keyword.replace(' ', '+')}",
                f"{self.base_url}/inventory?keyword={keyword.replace(' ', '+')}",
                f"{self.base_url}/?s={keyword.replace(' ', '+')}",
            ]
            
            for search_url in urls_to_try:
                try:
                    self.driver.get(search_url)
                    time.sleep(5)
                    
                    # Verifica se a página carregou resultados
                    page_source = self.driver.page_source
                    if keyword.lower() in page_source.lower() and len(page_source) > 5000:
                        break
                except:
                    continue
            
            results = []
            
            # Tenta encontrar cards de resultado com vários seletores
            selectors = [
                'a[href*="/item-detail/"]',
                'a[href*="/lot/"]',
                'a[href*="/inventory/"]',
                '.inventory-item a',
                '.lot-card a',
                '.search-result a'
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for elem in elements[:20]:
                            try:
                                title = elem.text.strip() or elem.get_attribute('title') or ''
                                link = elem.get_attribute('href') or ''
                                
                                if not title or not link:
                                    continue
                                    
                                item_id = f"jjkane_{hash(link) % 100000}"
                                results.append({
                                    "id": item_id,
                                    "site": self.site_name,
                                    "title": title,
                                    "link": link,
                                    "price": "Consultar no site",
                                    "keyword": keyword
                                })
                            except:
                                continue
                        if results:
                            break
                except:
                    continue
                    
            logger.info(f"Encontrados {len(results)} itens no {self.site_name} para '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Erro no Selenium para {self.site_name}: {e}")
            return []
            
    def _search_fallback(self, keyword):
        """Fallback usando requests."""
        logger.info(f"Usando fallback para {self.site_name}...")
        
        urls_to_try = [
            (f"{self.base_url}/search", {"q": keyword}),
            (f"{self.base_url}/inventory", {"keyword": keyword}),
        ]
        
        for url, params in urls_to_try:
            soup = self.fetch_page(url, params=params)
            if not soup:
                continue
                
            results = []
            links = soup.find_all('a', href=re.compile(r'/(item-detail|lot|inventory)/'))
            
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
                        
                    item_id = f"jjkane_{hash(href) % 100000}"
                    results.append({
                        "id": item_id,
                        "site": self.site_name,
                        "title": title,
                        "link": f"{self.base_url}{href}" if not href.startswith('http') else href,
                        "price": "Consultar no site",
                        "keyword": keyword
                    })
                except:
                    continue
                    
            if results:
                logger.info(f"Fallback encontrou {len(results)} itens no {self.site_name}")
                return results
                
        logger.info(f"Nenhum resultado encontrado no {self.site_name} para '{keyword}'")
        return []
        
    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
