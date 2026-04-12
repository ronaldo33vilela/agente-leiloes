from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
from .relevance_filter import filter_items
import re

class BidSpotterScraper(BaseScraper):
    """
    Scraper para o site BidSpotter.
    Usa requests + BeautifulSoup (sem Selenium).
    
    Estratégia (atualizada 2026-04):
    1. Busca via /en-us/search-results?searchTerm= (formulário real do site)
    2. Extrai lotes usando atributo data-lot-id nos elementos HTML
    3. Fallback: busca links de catálogos com padrão /auction-catalogues/.../lot-
    4. Filtra apenas leilões ATIVOS (ignora closed/ended/sold)
    """
    
    def __init__(self):
        super().__init__("BidSpotter")
        self.base_url = "https://www.bidspotter.com"
        
    def search(self, keyword):
        """Busca itens no BidSpotter usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Estratégia principal: search-results (URL real do formulário)
        results = self._search_results_page(keyword)
        if results:
            return results
        
        logger.info(f"Nenhum resultado ATIVO encontrado no {self.site_name} para '{keyword}'")
        return []
    
    def _search_results_page(self, keyword):
        """Busca via /en-us/search-results?searchTerm= (URL real do formulário do site)."""
        search_url = f"{self.base_url}/en-us/search-results"
        params = {"searchTerm": keyword}
        
        soup = self.fetch_page(search_url, params=params)
        if not soup:
            logger.warning(f"Falha ao acessar search-results do {self.site_name}")
            return []
        
        # Verificar se redirecionou para página de erro
        title_tag = soup.find('title')
        if title_tag and 'error' in title_tag.get_text().lower():
            logger.warning(f"Página de erro no {self.site_name}")
            return []
        
        results = []
        processed_ids = set()
        
        # Estratégia 1: Extrair lotes via data-lot-id (mais confiável)
        lot_elements = soup.find_all(attrs={"data-lot-id": True})
        logger.info(f"Encontrados {len(lot_elements)} elementos com data-lot-id")
        
        for el in lot_elements:
            try:
                lot_id = el.get('data-lot-id', '')
                if not lot_id or lot_id in processed_ids:
                    continue
                
                # Extrair título - procurar em links e headings dentro do elemento
                title = self._extract_lot_title(el)
                if not title or len(title) < 3 or title == 'No Image':
                    continue
                
                # Limpar números de lote grudados no início do título (ex: "139Clubcar Golf cart")
                title = re.sub(r'^\d+', '', title).strip()
                if not title:
                    continue
                
                # Extrair link
                link = self._extract_lot_link(el)
                if not link:
                    continue
                
                # Verificar se é leilão ativo
                element_text = el.get_text()
                if not should_include_item(element_text, title):
                    logger.debug(f"Item descartado (leilão finalizado): {title}")
                    continue
                
                processed_ids.add(lot_id)
                
                # Extrair preço
                price = self._extract_price(el)
                
                full_link = link if link.startswith('http') else f"{self.base_url}{link}"
                
                results.append({
                    "id": f"bidspotter_{lot_id[:12]}",
                    "site": self.site_name,
                    "title": title,
                    "link": full_link,
                    "price": price,
                    "keyword": keyword
                })
            except Exception as e:
                logger.debug(f"Erro ao processar lote: {e}")
                continue
        
        # Estratégia 2 (fallback): Buscar links de catálogos com lot-details
        if not results:
            results = self._extract_catalog_links(soup, keyword)
        
        if results:
            # Filtrar por relevância
            results = filter_items(results, keyword, min_score=0.5)
            logger.info(f"Encontrados {len(results)} itens ATIVOS e relevantes no {self.site_name}")
        
        return results
    
    def _extract_lot_title(self, element):
        """Extrai título do lote de um elemento."""
        # Procurar em headings primeiro
        for tag in ['h2', 'h3', 'h4', 'h5']:
            heading = element.find(tag)
            if heading:
                text = heading.get_text(strip=True)
                if text and len(text) > 3 and text != 'No Image':
                    return text
        
        # Procurar em links com texto significativo
        for link in element.find_all('a', href=True):
            text = link.get_text(strip=True)
            if text and len(text) > 5 and text != 'No Image' and not text.startswith('http'):
                return text
        
        # Procurar em alt de imagens
        img = element.find('img', alt=True)
        if img:
            alt = img.get('alt', '').strip()
            if alt and len(alt) > 5 and alt not in ['No Image', 'Loading...']:
                return alt
        
        return ''
    
    def _extract_lot_link(self, element):
        """Extrai link do lote de um elemento."""
        # Procurar link de catálogo/lote
        for link in element.find_all('a', href=True):
            href = link['href']
            if '/auction-catalogues/' in href or '/lot' in href.lower():
                return href
        
        # Qualquer link válido
        for link in element.find_all('a', href=True):
            href = link['href']
            if href and href != '#' and not href.startswith('javascript:'):
                return href
        
        return ''
    
    def _extract_catalog_links(self, soup, keyword):
        """Fallback: extrai links de catálogos com padrão /auction-catalogues/."""
        results = []
        processed = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/auction-catalogues/' not in href:
                continue
            if 'lot' not in href.lower():
                continue
            if href in processed:
                continue
            
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            
            # Limpar números grudados
            title = re.sub(r'^\d+', '', title).strip()
            if not title:
                continue
            
            element_text = link.parent.get_text() if link.parent else ""
            if not should_include_item(element_text, title):
                continue
            
            processed.add(href)
            price = self._extract_price(link)
            full_link = href if href.startswith('http') else f"{self.base_url}{href}"
            
            results.append({
                "id": f"bidspotter_{hash(href) % 100000}",
                "site": self.site_name,
                "title": title,
                "link": full_link,
                "price": price,
                "keyword": keyword
            })
        
        return results
    
    def _extract_price(self, element):
        """Extrai preço do contexto próximo a um elemento."""
        # Procurar no próprio elemento
        price_match = re.search(r'[\$£€][\d,]+\.?\d*', element.get_text())
        if price_match:
            return price_match.group(0)
        
        # Procurar nos pais
        parent = element
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            price_match = re.search(r'[\$£€][\d,]+\.?\d*', parent.get_text())
            if price_match:
                return price_match.group(0)
        
        return "Consultar no site"
