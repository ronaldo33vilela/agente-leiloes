from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
import re

class JJKaneScraper(BaseScraper):
    """
    Scraper para o site JJ Kane Auctions.
    Usa requests + BeautifulSoup (sem Selenium).
    
    Estratégia:
    1. Tenta múltiplas URLs de busca com requests
    2. Parsing HTML dos resultados
    3. Filtra apenas leilões ATIVOS (ignora closed/ended/sold)
    """
    
    def __init__(self):
        super().__init__("JJ Kane")
        self.base_url = "https://www.jjkane.com"
        
    def search(self, keyword):
        """Busca itens no JJ Kane usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Tenta múltiplas URLs de busca
        urls_to_try = [
            (f"{self.base_url}/search", {"q": keyword}),
            (f"{self.base_url}/inventory", {"keyword": keyword}),
            (f"{self.base_url}/", {"s": keyword}),
        ]
        
        for url, params in urls_to_try:
            try:
                results = self._search_url(url, params, keyword)
                if results:
                    return results
            except Exception as e:
                logger.error(f"Erro ao buscar em {url}: {e}")
                continue
        
        logger.info(f"Nenhum resultado ATIVO encontrado no {self.site_name} para '{keyword}'")
        return []
    
    def _search_url(self, url, params, keyword):
        """Busca em uma URL específica e extrai resultados."""
        soup = self.fetch_page(url, params=params)
        if not soup:
            return []
        
        # Verifica se a página tem conteúdo relevante
        page_text = soup.get_text().lower()
        if keyword.lower() not in page_text and len(page_text) < 1000:
            return []
        
        results = []
        processed = set()
        
        # Padrões de links para itens de leilão
        link_patterns = [
            re.compile(r'/(item-detail|lot|inventory|equipment)/'),
            re.compile(r'/auction/'),
            re.compile(r'/listing/'),
        ]
        
        for pattern in link_patterns:
            links = soup.find_all('a', href=pattern)
            
            for link_elem in links:
                try:
                    href = link_elem.get('href', '')
                    if href in processed:
                        continue
                    
                    # Extrai título de múltiplas fontes
                    title = self._extract_title(link_elem)
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
                    
                    item_id = f"jjkane_{hash(href) % 100000}"
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
                break
        
        # Se não encontrou com padrões específicos, tenta busca genérica
        if not results:
            results = self._generic_search(soup, keyword)
        
        logger.info(f"Encontrados {len(results)} itens ATIVOS no {self.site_name} para '{keyword}'")
        return results
    
    def _generic_search(self, soup, keyword):
        """Busca genérica quando os padrões específicos não funcionam."""
        results = []
        processed = set()
        
        # Busca todos os links que contenham a keyword no texto ou no href
        all_links = soup.find_all('a', href=True)
        
        for link_elem in all_links:
            try:
                href = link_elem.get('href', '')
                text = link_elem.text.strip()
                
                # Filtra links relevantes
                if href in processed or not text or len(text) < 5:
                    continue
                if href.startswith('#') or href.startswith('javascript:'):
                    continue
                if keyword.lower() not in text.lower() and keyword.lower() not in href.lower():
                    continue
                
                # Filtra apenas leilões ativos
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, text):
                    logger.debug(f"Item descartado (leilão finalizado): {text}")
                    continue
                
                processed.add(href)
                
                item_id = f"jjkane_{hash(href) % 100000}"
                full_link = f"{self.base_url}{href}" if not href.startswith('http') else href
                
                results.append({
                    "id": item_id,
                    "site": self.site_name,
                    "title": text[:200],
                    "link": full_link,
                    "price": "Consultar no site",
                    "keyword": keyword
                })
            except Exception:
                continue
        
        return results[:20]
    
    def _extract_title(self, element):
        """Extrai título de um elemento link."""
        # 1. Texto direto do link
        title = element.text.strip()
        
        # 2. Atributo title
        if not title:
            title = element.get('title', '')
        
        # 3. Atributo aria-label
        if not title:
            title = element.get('aria-label', '')
        
        # 4. Heading dentro do link
        if not title:
            heading = element.find(['h1', 'h2', 'h3', 'h4', 'h5', 'span'])
            if heading:
                title = heading.text.strip()
        
        return title
    
    def _extract_price(self, element):
        """Extrai preço do contexto próximo a um elemento."""
        parent = element
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            price_match = re.search(r'\$[\d,]+\.?\d*', parent.text)
            if price_match:
                return price_match.group(0)
        return "Consultar no site"
