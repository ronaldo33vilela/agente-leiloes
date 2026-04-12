from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
from .relevance_filter import filter_items
import re
import json

class BidSpotterScraper(BaseScraper):
    """
    Scraper para o site BidSpotter.
    Usa requests + BeautifulSoup (sem Selenium).
    
    Estratégia:
    1. Tenta a API interna de busca do BidSpotter (JSON)
    2. Fallback para scraping HTML da página de busca
    3. Filtra apenas leilões ATIVOS (ignora closed/ended/sold)
    """
    
    def __init__(self):
        super().__init__("BidSpotter")
        self.base_url = "https://www.bidspotter.com"
        
    def search(self, keyword):
        """Busca itens no BidSpotter usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Tenta a API JSON primeiro
        results = self._search_api(keyword)
        if results:
            return results
        
        # Fallback para scraping HTML
        return self._search_html(keyword)
    
    def _search_api(self, keyword):
        """Tenta buscar via API interna do BidSpotter."""
        try:
            # BidSpotter pode ter uma API de busca interna
            api_url = f"{self.base_url}/api/search"
            params = {"query": keyword, "limit": 20}
            
            # Adiciona headers específicos para API
            headers = {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            try:
                response = self.session.get(api_url, params=params, timeout=15, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    
                    items = data if isinstance(data, list) else data.get('results', data.get('items', []))
                    
                    for item in items[:20]:
                        title = item.get('title', item.get('name', ''))
                        link = item.get('url', item.get('link', ''))
                        price = item.get('price', item.get('currentBid', 'Consultar no site'))
                        item_id = item.get('id', str(hash(link) % 100000))
                        status = item.get('status', '').lower()
                        
                        # Filtra apenas leilões ativos
                        if status in ['closed', 'ended', 'sold', 'completed', 'expired']:
                            logger.debug(f"Item descartado (status={status}): {title}")
                            continue
                        
                        if title and link:
                            if not link.startswith('http'):
                                link = f"{self.base_url}{link}"
                            results.append({
                                "id": f"bidspotter_{item_id}",
                                "site": self.site_name,
                                "title": title,
                                "link": link,
                                "price": str(price),
                                "keyword": keyword
                            })
                    
                    if results:
                        # Filtrar por relevância
                        results = filter_items(results, keyword, min_score=0.5)
                        logger.info(f"API encontrou {len(results)} itens ATIVOS no {self.site_name}")
                        return results
            except Exception:
                pass
            
            return []
            
        except Exception as e:
            logger.error(f"Erro na busca API do {self.site_name}: {e}")
            return []
    
    def _search_html(self, keyword):
        """Busca usando scraping HTML."""
        logger.info(f"Usando busca HTML para {self.site_name}...")
        
        # Tenta múltiplas URLs de busca
        urls_to_try = [
            (f"{self.base_url}/en-us/search", {"query": keyword}),
            (f"{self.base_url}/en-us/search", {"q": keyword}),
            (f"{self.base_url}/search", {"query": keyword}),
        ]
        
        for search_url, params in urls_to_try:
            soup = self.fetch_page(search_url, params=params)
            if not soup:
                continue
            
            results = []
            processed = set()
            
            # Busca links de lotes/catálogos
            link_patterns = [
                re.compile(r'/auction-catalogues/.*lot-details'),
                re.compile(r'/lot/'),
                re.compile(r'/en-us/auction'),
            ]
            
            for pattern in link_patterns:
                links = soup.find_all('a', href=pattern)
                
                for link_elem in links:
                    try:
                        href = link_elem.get('href', '')
                        if href in processed:
                            continue
                        
                        title = link_elem.text.strip() or link_elem.get('title', '')
                        if not title or len(title) < 3:
                            continue
                        
                        # Filtra apenas leilões ativos
                        element_context = link_elem.parent.get_text() if link_elem.parent else ""
                        if not should_include_item(element_context, title):
                            logger.debug(f"Item descartado (leilão finalizado): {title}")
                            continue
                        
                        processed.add(href)
                        
                        # Busca preço no contexto
                        price = self._extract_price(link_elem)
                        
                        item_id = f"bidspotter_{hash(href) % 100000}"
                        full_link = f"{self.base_url}{href}" if not href.startswith('http') else href
                        
                        results.append({
                            "id": item_id,
                            "site": self.site_name,
                            "title": title,
                            "link": full_link,
                            "price": price,
                            "keyword": keyword
                        })
                    except Exception:
                        continue
            
            if results:
                # Filtrar por relevância
                results = filter_items(results, keyword, min_score=0.5)
                logger.info(f"HTML encontrou {len(results)} itens ATIVOS no {self.site_name}")
                return results
        
        logger.info(f"Nenhum resultado ATIVO encontrado no {self.site_name} para '{keyword}'")
        return []
    
    def _extract_price(self, element):
        """Extrai preço do contexto próximo a um elemento."""
        parent = element
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            price_match = re.search(r'[\$£€][\d,]+\.?\d*', parent.text)
            if price_match:
                return price_match.group(0)
        return "Consultar no site"
