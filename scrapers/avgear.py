from .base_scraper import BaseScraper, logger
import re
import json

class AVGearScraper(BaseScraper):
    """
    Scraper para o site AVGear.
    AVGear é um site de equipamentos audiovisuais.
    Tentamos a API JSON do Shopify e fallback para HTML.
    """
    
    def __init__(self):
        super().__init__("AVGear")
        self.base_url = "https://www.avgear.com"
        
    def search(self, keyword):
        """Busca itens no AVGear."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        # Tenta a API JSON do Shopify
        results = self._search_json(keyword)
        if results:
            return results
            
        # Fallback para scraping HTML
        return self._search_html(keyword)
        
    def _search_json(self, keyword):
        """Busca usando a API JSON do Shopify (search/suggest.json)."""
        try:
            search_url = f"{self.base_url}/search/suggest.json"
            params = {
                "q": keyword,
                "resources[type]": "product",
                "resources[limit]": 20
            }
            
            response = self.session.get(search_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            results = []
            products = data.get('resources', {}).get('results', {}).get('products', [])
            
            for product in products:
                product_id = product.get('id', '')
                title = product.get('title', '')
                handle = product.get('handle', '')
                price = product.get('price', '')
                
                if price:
                    try:
                        price_float = float(price)
                        price_str = f"${price_float:,.2f}"
                    except:
                        price_str = f"${price}"
                else:
                    price_str = "Consultar no site"
                    
                results.append({
                    "id": f"avgear_{product_id}",
                    "site": self.site_name,
                    "title": title,
                    "link": f"{self.base_url}/products/{handle}",
                    "price": price_str,
                    "keyword": keyword
                })
                
            logger.info(f"Encontrados {len(results)} itens no {self.site_name} (JSON) para '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Erro na busca JSON do {self.site_name}: {e}")
            return []
            
    def _search_html(self, keyword):
        """Fallback: busca usando scraping HTML com seletores melhorados."""
        search_url = f"{self.base_url}/search"
        params = {"q": keyword, "type": "product"}
        
        soup = self.fetch_page(search_url, params=params)
        if not soup:
            return []
            
        results = []
        processed_ids = set()
        
        # Encontra todos os links de produtos
        product_links = soup.find_all('a', href=re.compile(r'/products/[^?]+'))
        
        for link_elem in product_links:
            try:
                href = link_elem.get('href', '')
                match = re.search(r'/products/([^?/]+)', href)
                if not match:
                    continue
                    
                product_slug = match.group(1)
                item_id = f"avgear_{product_slug}"
                
                if item_id in processed_ids:
                    continue
                processed_ids.add(item_id)
                
                # Título: tenta múltiplas fontes
                title = ''
                
                # 1. Atributo title ou aria-label do link
                title = link_elem.get('title', '') or link_elem.get('aria-label', '')
                
                # 2. Texto direto do link
                if not title:
                    title = link_elem.text.strip()
                    
                # 3. Elemento h2/h3/h4 dentro ou próximo do link
                if not title:
                    heading = link_elem.find(['h2', 'h3', 'h4', 'span'])
                    if heading:
                        title = heading.text.strip()
                        
                # 4. Gera título a partir do slug
                if not title:
                    title = product_slug.replace('-', ' ').title()
                
                # Preço: busca no contexto do card pai
                price_text = "Consultar no site"
                parent = link_elem.parent
                for _ in range(3):  # Sobe até 3 níveis
                    if parent is None:
                        break
                    price_match = re.search(r'\$(\d+(?:,\d+)*\.\d{2})', parent.text)
                    if price_match and float(price_match.group(1).replace(',', '')) > 0:
                        price_text = f"${price_match.group(1)}"
                        break
                    parent = parent.parent
                
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
                
        logger.info(f"Encontrados {len(results)} itens no {self.site_name} (HTML) para '{keyword}'")
        return results
