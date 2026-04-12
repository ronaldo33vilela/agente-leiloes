from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
from .relevance_filter import filter_items
import re
import json

class GovDealsScraper(BaseScraper):
    """
    Scraper para o site GovDeals.
    Usa requests + BeautifulSoup (sem Selenium).
    
    NOTA (2026-04): GovDeals migrou para SPA Angular. O conteúdo é renderizado
    via JavaScript, então requests simples retornam HTML vazio. A API interna
    (/api/search/assets) retorna 406 sem headers específicos de autenticação.
    
    Estratégia atualizada:
    1. Tenta a API interna com headers Angular
    2. Tenta busca via URL antiga ColdFusion (pode ainda funcionar em deploy)
    3. Tenta busca via allsurplus.com (mesmo grupo/empresa)
    4. Retorna resultados encontrados ou lista vazia com log detalhado
    """
    
    def __init__(self):
        super().__init__("GovDeals")
        self.base_url = "https://www.govdeals.com"
        
    def search(self, keyword):
        """Busca itens no GovDeals usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Estratégia 1: API interna com headers Angular
        results = self._search_api(keyword)
        if results:
            return results
        
        # Estratégia 2: AllSurplus (mesmo grupo)
        results = self._search_allsurplus(keyword)
        if results:
            return results
        
        # Estratégia 3: URL antiga ColdFusion
        results = self._search_cfm(keyword)
        if results:
            return results
        
        logger.info(f"Nenhum resultado encontrado no {self.site_name} para '{keyword}' (site usa SPA Angular)")
        return []
    
    def _search_api(self, keyword):
        """Tenta buscar via API interna do GovDeals com headers Angular."""
        try:
            api_url = f"{self.base_url}/api/search/assets"
            
            # Headers que simulam chamada Angular/SPA
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/en/search?q={keyword.replace(' ', '+')}",
            }
            
            params = {
                "q": keyword,
                "page": "1",
                "pageSize": "25",
                "sort": "closing_soon"
            }
            
            try:
                response = self.session.get(api_url, params=params, timeout=15, headers=headers)
                if response.status_code == 200:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        data = response.json()
                        return self._parse_api_results(data, keyword)
            except Exception as e:
                logger.debug(f"API GET falhou: {e}")
            
            # Tentar POST
            try:
                payload = {
                    "query": keyword,
                    "page": 1,
                    "pageSize": 25,
                    "sort": "closing_soon"
                }
                response = self.session.post(api_url, json=payload, timeout=15, headers=headers)
                if response.status_code == 200:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        data = response.json()
                        return self._parse_api_results(data, keyword)
            except Exception as e:
                logger.debug(f"API POST falhou: {e}")
            
            return []
            
        except Exception as e:
            logger.debug(f"Erro na busca API do {self.site_name}: {e}")
            return []
    
    def _parse_api_results(self, data, keyword):
        """Parseia resultados da API JSON."""
        results = []
        
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ['results', 'items', 'assets', 'data', 'hits']:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
        
        for item in items[:25]:
            try:
                title = item.get('title', item.get('name', item.get('description', '')))
                link = item.get('url', item.get('link', item.get('detailUrl', '')))
                price = item.get('price', item.get('currentBid', item.get('minimumBid', 'Consultar no site')))
                item_id = item.get('id', item.get('assetId', str(hash(str(item)) % 100000)))
                status = str(item.get('status', '')).lower()
                
                if status in ['closed', 'ended', 'sold', 'completed', 'expired']:
                    continue
                
                if title and link:
                    if not link.startswith('http'):
                        link = f"{self.base_url}{link}"
                    results.append({
                        "id": f"govdeals_{item_id}",
                        "site": self.site_name,
                        "title": title,
                        "link": link,
                        "price": str(price),
                        "keyword": keyword
                    })
            except Exception:
                continue
        
        if results:
            results = filter_items(results, keyword, min_score=0.5)
            logger.info(f"API encontrou {len(results)} itens no {self.site_name}")
        
        return results
    
    def _search_allsurplus(self, keyword):
        """Busca via AllSurplus.com (mesmo grupo que GovDeals)."""
        try:
            # AllSurplus é o marketplace unificado que inclui GovDeals
            search_url = "https://www.allsurplus.com/en/search"
            params = {"q": keyword, "sort": "closing_soon"}
            
            soup = self.fetch_page(search_url, params=params)
            if not soup:
                return []
            
            results = []
            processed = set()
            
            # Procurar links de assets
            asset_links = soup.find_all('a', href=re.compile(r'/en/asset/|/asset/'))
            
            for link_elem in asset_links:
                try:
                    href = link_elem.get('href', '')
                    title = link_elem.get('title', '').strip() or link_elem.text.strip()
                    
                    if not title or href in processed or len(title) < 3:
                        continue
                    
                    element_context = link_elem.parent.get_text() if link_elem.parent else ""
                    if not should_include_item(element_context, title):
                        continue
                    
                    processed.add(href)
                    parts = href.strip('/').split('/')
                    lot_id = '_'.join(parts[-2:]) if len(parts) >= 2 else str(hash(href) % 100000)
                    price = self._extract_price(link_elem)
                    full_link = href if href.startswith('http') else f"https://www.allsurplus.com{href}"
                    
                    results.append({
                        "id": f"govdeals_{lot_id}",
                        "site": self.site_name,
                        "title": title,
                        "link": full_link,
                        "price": price,
                        "keyword": keyword
                    })
                except Exception:
                    continue
            
            if results:
                results = filter_items(results, keyword, min_score=0.5)
                logger.info(f"AllSurplus encontrou {len(results)} itens para '{keyword}'")
            
            return results
            
        except Exception as e:
            logger.debug(f"Erro na busca AllSurplus: {e}")
            return []
    
    def _search_cfm(self, keyword):
        """Busca via URL antiga ColdFusion (pode funcionar em alguns ambientes)."""
        try:
            api_url = f"{self.base_url}/index.cfm"
            params = {
                "fa": "Main.AdvSearchResultsNew",
                "searchtext": keyword,
                "rowCount": "25",
                "StartRow": "1"
            }
            
            soup = self.fetch_page(api_url, params=params)
            if not soup:
                return []
            
            results = []
            processed = set()
            
            asset_links = soup.find_all('a', href=re.compile(r'(itemid=|/en/asset/|/asset/)'))
            
            for link_elem in asset_links:
                try:
                    href = link_elem.get('href', '')
                    title = link_elem.get('title', '').strip() or link_elem.text.strip()
                    
                    if not title or href in processed or len(title) < 3:
                        continue
                    
                    element_context = link_elem.parent.get_text() if link_elem.parent else ""
                    if not should_include_item(element_context, title):
                        continue
                    
                    processed.add(href)
                    
                    id_match = re.search(r'itemid=(\d+)', href)
                    lot_id = id_match.group(1) if id_match else str(hash(href) % 100000)
                    price = self._extract_price(link_elem)
                    full_link = href if href.startswith('http') else f"{self.base_url}{href}"
                    
                    results.append({
                        "id": f"govdeals_{lot_id}",
                        "site": self.site_name,
                        "title": title,
                        "link": full_link,
                        "price": price,
                        "keyword": keyword
                    })
                except Exception:
                    continue
            
            if results:
                results = filter_items(results, keyword, min_score=0.5)
                logger.info(f"CFM encontrou {len(results)} itens no {self.site_name}")
            
            return results
            
        except Exception as e:
            logger.debug(f"Erro na busca CFM: {e}")
            return []
    
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
