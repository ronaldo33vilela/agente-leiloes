from .base_scraper import BaseScraper, logger
import re
import json

class GovDealsScraper(BaseScraper):
    """
    Scraper para o site GovDeals.
    O GovDeals usa Angular (SPA), então o HTML estático não contém os resultados.
    Usamos Selenium para renderizar a página e extrair os dados via JavaScript.
    """
    
    def __init__(self):
        super().__init__("GovDeals")
        self.base_url = "https://www.govdeals.com"
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
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("Selenium WebDriver inicializado para GovDeals.")
        except Exception as e:
            logger.error(f"Erro ao inicializar Selenium: {e}")
            self.driver = None
        
    def search(self, keyword):
        """Busca itens no GovDeals usando Selenium."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        self._init_driver()
        if not self.driver:
            logger.warning("Selenium não disponível. Tentando fallback com requests...")
            return self._search_fallback(keyword)
        
        try:
            import time
            
            search_url = f"{self.base_url}/en/search?q={keyword.replace(' ', '+')}&sort=closing_soon"
            self.driver.get(search_url)
            
            # Espera os cards carregarem (até 10 segundos)
            time.sleep(10)
            
            # Extrai dados via JavaScript - script melhorado
            script = """
            const cards = document.querySelectorAll('.card-search');
            let results = [];
            cards.forEach((card) => {
                const titleEl = card.querySelector('a[name="lnkImageAssetDetails"]');
                const linkEl = card.querySelector('a[href*="/en/asset/"]');
                
                let title = titleEl ? (titleEl.getAttribute('title') || titleEl.textContent.trim()) : '';
                let link = linkEl ? linkEl.getAttribute('href') : '';
                
                // Extrai preço de forma mais precisa
                let priceEl = card.querySelector('.price-amount, .current-bid, [class*="price"]');
                let price = '';
                if (priceEl) {
                    let priceText = priceEl.textContent.trim();
                    let match = priceText.match(/USD\\s*[\\d,]+\\.\\d{2}/);
                    if (match) price = match[0];
                }
                
                // Fallback: busca no texto do card
                if (!price) {
                    let cardText = card.textContent;
                    let match = cardText.match(/USD\\s*([\\d,]+\\.\\d{2})(?![\\d])/);
                    if (match) price = 'USD ' + match[1];
                }
                
                // Extrai lot number
                let lotText = card.textContent;
                let lotMatch = lotText.match(/Lot#:\\s*([\\d-]+)/);
                let lot = lotMatch ? lotMatch[1] : '';
                
                // Extrai localização
                let locMatch = lotText.match(/([A-Z][a-z]+(?:\\s[A-Z][a-z]+)*,\\s*[A-Za-z]+(?:\\s[A-Za-z]+)*,\\s*USA)/);
                let location = locMatch ? locMatch[1] : '';
                
                if (title && link) {
                    results.push({title, link, price, lot, location});
                }
            });
            return JSON.stringify(results);
            """
            
            result_json = self.driver.execute_script(script)
            items = json.loads(result_json)
            
            results = []
            for item in items:
                lot_id = item.get('lot', '').replace('-', '_')
                if not lot_id:
                    lot_id = item['link'].replace('/', '_')
                    
                results.append({
                    "id": f"govdeals_{lot_id}",
                    "site": self.site_name,
                    "title": item['title'],
                    "link": f"{self.base_url}{item['link']}",
                    "price": item['price'] or "Preço não disponível",
                    "location": item.get('location', ''),
                    "keyword": keyword
                })
                
            logger.info(f"Encontrados {len(results)} itens no {self.site_name} para '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Erro no Selenium para {self.site_name}: {e}")
            return self._search_fallback(keyword)
            
    def _search_fallback(self, keyword):
        """Fallback usando requests para quando o Selenium não estiver disponível."""
        logger.info(f"Usando fallback (requests) para {self.site_name}...")
        
        search_url = f"{self.base_url}/en/search"
        params = {"q": keyword, "sort": "closing_soon"}
        
        soup = self.fetch_page(search_url, params=params)
        if not soup:
            return []
            
        results = []
        links = soup.find_all('a', href=re.compile(r'/en/asset/'))
        processed = set()
        
        for link_elem in links:
            try:
                href = link_elem.get('href', '')
                title = link_elem.get('title', '').strip()
                
                if not title or href in processed:
                    continue
                    
                processed.add(href)
                parts = href.strip('/').split('/')
                lot_id = '_'.join(parts[-2:]) if len(parts) >= 2 else href
                
                results.append({
                    "id": f"govdeals_{lot_id}",
                    "site": self.site_name,
                    "title": title,
                    "link": f"{self.base_url}{href}",
                    "price": "Preço não disponível (requer JavaScript)",
                    "keyword": keyword
                })
            except Exception as e:
                logger.error(f"Erro no fallback: {e}")
                
        logger.info(f"Fallback encontrou {len(results)} itens no {self.site_name}")
        return results
        
    def __del__(self):
        """Fecha o driver ao destruir o objeto."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
