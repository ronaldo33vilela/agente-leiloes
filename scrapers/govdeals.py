from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
import re
import json

class GovDealsScraper(BaseScraper):
    """
    Scraper para o site GovDeals.
    Usa requests + BeautifulSoup (sem Selenium).
    
    Estratégia:
    1. Tenta a API interna de busca do GovDeals (JSON)
    2. Fallback para scraping HTML da página de busca
    3. Filtra apenas leilões ATIVOS (ignora closed/ended/sold)
    """
    
    def __init__(self):
        super().__init__("GovDeals")
        self.base_url = "https://www.govdeals.com"
        
    def search(self, keyword):
        """Busca itens no GovDeals usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Tenta a API JSON primeiro (mais confiável)
        results = self._search_api(keyword)
        if results:
            return results
        
        # Fallback para scraping HTML
        return self._search_html(keyword)
    
    def _search_api(self, keyword):
        """Tenta buscar via API interna do GovDeals."""
        try:
            # GovDeals usa uma API interna para busca
            api_url = f"{self.base_url}/index.cfm"
            params = {
                "fa": "Main.AdvSearchResultsNew",
                "searchPg": "Main",
                "kession": "",
                "category": "00",
                "subcategory": "00",
                "searchtext": keyword,
                "sortOption": "ad",
                "timing": "ByClosing",
                "rowCount": "20",
                "StartRow": "1"
            }
            
            soup = self.fetch_page(api_url, params=params)
            if not soup:
                return []
            
            results = []
            processed = set()
            
            # Busca links de assets na página de resultados
            # GovDeals usa links no formato /index.cfm?fa=Main.Item&itemid=XXX ou /en/asset/XXX
            asset_links = soup.find_all('a', href=re.compile(r'(itemid=|/en/asset/|/asset/)'))
            
            for link_elem in asset_links:
                try:
                    href = link_elem.get('href', '')
                    title = link_elem.get('title', '').strip() or link_elem.text.strip()
                    
                    if not title or href in processed or len(title) < 3:
                        continue
                    
                    # Filtra apenas leilões ativos
                    element_context = link_elem.parent.get_text() if link_elem.parent else ""
                    if not should_include_item(element_context, title):
                        logger.debug(f"Item descartado (leilão finalizado): {title}")
                        continue
                    
                    processed.add(href)
                    
                    # Extrai ID do item
                    id_match = re.search(r'itemid=(\d+)', href)
                    if id_match:
                        lot_id = id_match.group(1)
                    else:
                        parts = href.strip('/').split('/')
                        lot_id = '_'.join(parts[-2:]) if len(parts) >= 2 else str(hash(href) % 100000)
                    
                    # Busca preço no contexto próximo
                    price = self._extract_price(link_elem)
                    
                    # Monta link completo
                    full_link = href if href.startswith('http') else f"{self.base_url}{href}"
                    
                    results.append({
                        "id": f"govdeals_{lot_id}",
                        "site": self.site_name,
                        "title": title,
                        "link": full_link,
                        "price": price,
                        "keyword": keyword
                    })
                except Exception as e:
                    logger.error(f"Erro ao processar item da API: {e}")
            
            logger.info(f"API encontrou {len(results)} itens ATIVOS no {self.site_name} para '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Erro na busca API do {self.site_name}: {e}")
            return []
    
    def _search_html(self, keyword):
        """Busca usando scraping HTML da página de busca."""
        logger.info(f"Usando busca HTML para {self.site_name}...")
        
        search_url = f"{self.base_url}/en/search"
        params = {"q": keyword, "sort": "closing_soon"}
        
        soup = self.fetch_page(search_url, params=params)
        if not soup:
            return []
            
        results = []
        processed = set()
        
        # Busca links de assets
        links = soup.find_all('a', href=re.compile(r'/en/asset/'))
        
        for link_elem in links:
            try:
                href = link_elem.get('href', '')
                title = link_elem.get('title', '').strip() or link_elem.text.strip()
                
                if not title or href in processed or len(title) < 3:
                    continue
                
                # Filtra apenas leilões ativos
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, title):
                    logger.debug(f"Item descartado (leilão finalizado): {title}")
                    continue
                    
                processed.add(href)
                parts = href.strip('/').split('/')
                lot_id = '_'.join(parts[-2:]) if len(parts) >= 2 else str(hash(href) % 100000)
                
                # Busca preço no contexto próximo
                price = self._extract_price(link_elem)
                
                results.append({
                    "id": f"govdeals_{lot_id}",
                    "site": self.site_name,
                    "title": title,
                    "link": f"{self.base_url}{href}",
                    "price": price,
                    "keyword": keyword
                })
            except Exception as e:
                logger.error(f"Erro no scraping HTML: {e}")
                
        logger.info(f"HTML encontrou {len(results)} itens ATIVOS no {self.site_name}")
        return results
    
    def _extract_price(self, element):
        """Extrai preço do contexto próximo a um elemento."""
        parent = element
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            price_match = re.search(r'(?:USD\s*)?[\$]?([\d,]+\.\d{2})', parent.text)
            if price_match:
                return f"USD {price_match.group(1)}"
        return "Consultar no site"
