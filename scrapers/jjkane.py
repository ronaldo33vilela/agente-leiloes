from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
from .relevance_filter import filter_items
import re

class JJKaneScraper(BaseScraper):
    """
    Scraper para o site JJ Kane Auctions.
    Usa requests + BeautifulSoup (sem Selenium).
    
    NOTA (2026-04): JJ Kane não tem busca funcional no site principal.
    /search e /inventory retornam 404. WordPress /?s= retorna 0 resultados.
    
    Estratégia atualizada:
    1. Busca via Proxibid (jjkane.proxibid.com) - catálogos de leilão
    2. Busca via categorias do site (/categories/...)
    3. Busca via WordPress search (fallback)
    4. Filtra apenas leilões ATIVOS
    """
    
    def __init__(self):
        super().__init__("JJ Kane")
        self.base_url = "https://www.jjkane.com"
        self.proxibid_url = "https://jjkane.proxibid.com"
        
    def search(self, keyword):
        """Busca itens no JJ Kane usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        all_results = []
        
        # Estratégia 1: Proxibid (catálogos de leilão ativos)
        proxibid_results = self._search_proxibid(keyword)
        all_results.extend(proxibid_results)
        
        # Estratégia 2: Categorias do site
        category_results = self._search_categories(keyword)
        all_results.extend(category_results)
        
        # Estratégia 3: WordPress search (fallback)
        if not all_results:
            wp_results = self._search_wordpress(keyword)
            all_results.extend(wp_results)
        
        # Deduplicar por título
        seen_titles = set()
        unique_results = []
        for item in all_results:
            title_key = item['title'].lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_results.append(item)
        
        # Filtrar por relevância
        unique_results = filter_items(unique_results, keyword, min_score=0.5)
        logger.info(f"Encontrados {len(unique_results)} itens ATIVOS no {self.site_name} para '{keyword}'")
        return unique_results
    
    def _search_proxibid(self, keyword):
        """Busca via Proxibid - catálogos de leilão JJ Kane."""
        results = []
        
        try:
            # Primeiro, obter lista de leilões ativos
            soup = self.fetch_page(self.proxibid_url)
            if not soup:
                logger.debug("Falha ao acessar Proxibid")
                return []
            
            # Encontrar links de catálogos de eventos
            catalog_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                txt = link.get_text(strip=True)
                if 'event-catalog' in href.lower() or 'event-catalo' in href.lower():
                    full_url = href if href.startswith('http') else f"{self.proxibid_url}{href}"
                    if full_url not in [c[0] for c in catalog_links]:
                        catalog_links.append((full_url, txt))
            
            logger.info(f"Encontrados {len(catalog_links)} catálogos Proxibid")
            
            # Acessar cada catálogo e buscar itens com a keyword
            for catalog_url, catalog_name in catalog_links[:3]:  # Limitar a 3 catalogos (velocidade)
                try:
                    catalog_results = self._search_proxibid_catalog(catalog_url, keyword)
                    results.extend(catalog_results)
                except Exception as e:
                    logger.debug(f"Erro no catálogo {catalog_name}: {e}")
                    continue
            
        except Exception as e:
            logger.debug(f"Erro na busca Proxibid: {e}")
        
        return results
    
    def _search_proxibid_catalog(self, catalog_url, keyword):
        """Busca itens em um catálogo Proxibid específico."""
        results = []
        
        soup = self.fetch_page(catalog_url)
        if not soup:
            return []
        
        keyword_lower = keyword.lower()
        processed = set()
        
        # Procurar texto da página que contenha a keyword
        page_text = soup.get_text()
        if keyword_lower not in page_text.lower():
            return []
        
        # Procurar itens/lotes
        # Proxibid usa divs com informações de lote
        for element in soup.find_all(['div', 'tr', 'li', 'a']):
            text = element.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            
            if keyword_lower not in text.lower():
                continue
            
            # Extrair link
            link = ''
            if element.name == 'a':
                link = element.get('href', '')
            else:
                a_tag = element.find('a', href=True)
                if a_tag:
                    link = a_tag['href']
            
            if not link:
                link = catalog_url
            
            if link.startswith('/'):
                link = f"{self.proxibid_url}{link}"
            
            # Extrair título (limpar e truncar)
            title = text[:200].strip()
            # Limpar números de lote no início
            title = re.sub(r'^\d+\s*[-–]\s*', '', title)
            title = re.sub(r'^Lot\s+\d+\s*[-–:]\s*', '', title, flags=re.IGNORECASE)
            
            if not title or len(title) < 5:
                continue
            
            title_key = title[:50].lower()
            if title_key in processed:
                continue
            processed.add(title_key)
            
            # Verificar se é ativo
            if not should_include_item(text, title):
                continue
            
            # Extrair preço
            price = 'Consultar no site'
            price_match = re.search(r'\$[\d,]+\.?\d*', text)
            if price_match:
                price = price_match.group(0)
            
            results.append({
                "id": f"jjkane_{hash(title_key) % 100000}",
                "site": self.site_name,
                "title": title[:150],
                "link": link,
                "price": price,
                "keyword": keyword
            })
        
        return results[:20]
    
    def _search_categories(self, keyword):
        """Busca via categorias do site JJ Kane."""
        results = []
        
        try:
            # Mapear keyword para possíveis categorias
            category_map = {
                'golf cart': 'motorcycles-atvs-golf-and-yard-carts',
                'golf': 'motorcycles-atvs-golf-and-yard-carts',
                'cart': 'motorcycles-atvs-golf-and-yard-carts',
                'atv': 'motorcycles-atvs-golf-and-yard-carts',
                'motorcycle': 'motorcycles-atvs-golf-and-yard-carts',
                'truck': 'pickup-trucks-and-service-trucks',
                'pickup': 'pickup-trucks-and-service-trucks',
                'dump truck': 'dump-trucks',
                'trailer': 'trailers',
                'excavator': 'excavators',
                'bulldozer': 'bulldozers',
                'crane': 'cranes',
                'backhoe': 'backhoes-and-loaders',
                'loader': 'backhoes-and-loaders',
                'car': 'cars',
                'suv': 'suvs',
                'van': 'vans',
                'electronics': 'electronics',
                'computer': 'computer',
                'audio': 'tv-video-and-audio',
                'video': 'tv-video-and-audio',
                'furniture': 'home-furniture',
                'tool': 'tools-attachments-parts-and-accessories',
                'equipment': 'industrial-machinery-equipment',
                'bucket truck': 'bucket-trucks',
                'wood chipper': 'wood-chippers',
                'trencher': 'trenchers',
                'flatbed': 'flatbed-trucks',
            }
            
            # Encontrar categorias relevantes
            keyword_lower = keyword.lower()
            matching_categories = set()
            
            for term, category in category_map.items():
                if term in keyword_lower or keyword_lower in term:
                    matching_categories.add(category)
            
            if not matching_categories:
                return []
            
            for category in matching_categories:
                try:
                    url = f"{self.base_url}/categories/{category}"
                    soup = self.fetch_page(url)
                    if not soup:
                        continue
                    
                    # Procurar itens na página de categoria
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        text = link.get_text(strip=True)
                        
                        if not text or len(text) < 5:
                            continue
                        
                        # Procurar links de itens
                        if any(k in href.lower() for k in ['lot', 'item', 'detail', 'equipment']):
                            if keyword_lower in text.lower():
                                full_link = href if href.startswith('http') else f"{self.base_url}{href}"
                                results.append({
                                    "id": f"jjkane_{hash(href) % 100000}",
                                    "site": self.site_name,
                                    "title": text[:200],
                                    "link": full_link,
                                    "price": "Consultar no site",
                                    "keyword": keyword
                                })
                except Exception as e:
                    logger.debug(f"Erro na categoria {category}: {e}")
                    continue
            
        except Exception as e:
            logger.debug(f"Erro na busca por categorias: {e}")
        
        return results
    
    def _search_wordpress(self, keyword):
        """Busca via WordPress search (fallback)."""
        results = []
        
        try:
            soup = self.fetch_page(self.base_url, params={"s": keyword})
            if not soup:
                return []
            
            # Procurar artigos/resultados
            for article in soup.find_all(['article', 'div'], class_=lambda c: c and 'result' in str(c).lower()):
                heading = article.find(['h1', 'h2', 'h3', 'h4'])
                if heading:
                    a_tag = heading.find('a', href=True)
                    if a_tag:
                        title = a_tag.get_text(strip=True)
                        href = a_tag['href']
                        if title and len(title) > 3:
                            full_link = href if href.startswith('http') else f"{self.base_url}{href}"
                            results.append({
                                "id": f"jjkane_{hash(href) % 100000}",
                                "site": self.site_name,
                                "title": title[:200],
                                "link": full_link,
                                "price": "Consultar no site",
                                "keyword": keyword
                            })
        except Exception as e:
            logger.debug(f"Erro na busca WordPress: {e}")
        
        return results
