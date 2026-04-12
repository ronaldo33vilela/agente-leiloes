from .base_scraper import BaseScraper, logger
import re
import urllib3

# Desabilita avisos de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PublicSurplusScraper(BaseScraper):
    """
    Scraper para o site Public Surplus.
    Usa requests + BeautifulSoup (sem Selenium).
    O site pode ter problemas de SSL, então usamos verify=False.
    """
    
    def __init__(self):
        super().__init__("Public Surplus")
        self.base_url = "https://www.publicsurplus.com"
        
    def search(self, keyword):
        """Busca itens no Public Surplus usando requests."""
        logger.info(f"Buscando '{keyword}' no {self.site_name}...")
        
        results = self._search_requests(keyword)
        logger.info(f"Encontrados {len(results)} itens no {self.site_name} para '{keyword}'")
        return results
        
    def _search_requests(self, keyword):
        """Busca usando requests com tratamento especial de SSL."""
        search_url = f"{self.base_url}/sms/browse/search"
        params = {
            "posting": "y",
            "keyword": keyword
        }
        
        try:
            # Tenta com verificação SSL desabilitada (site tem problemas de certificado)
            response = self.session.get(search_url, params=params, timeout=20, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao acessar {self.site_name}: {e}")
            return []
            
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        del response
        
        return self._parse_results(soup, keyword)
        
    def _parse_results(self, soup, keyword=""):
        """Extrai resultados do HTML do Public Surplus."""
        results = []
        processed_ids = set()
        
        # Encontra os links de resultados
        links = soup.find_all('a', href=re.compile(r'/sms/auction/view\?auc='))
        
        for link_elem in links:
            try:
                href = link_elem['href']
                text = link_elem.text.strip()
                
                # Ignora links que são apenas "View Images" ou vazios
                if not text or "View Images" in text or len(text) < 5:
                    continue
                    
                # Extrai o ID do leilão
                match = re.search(r'auc=(\d+)', href)
                if not match:
                    continue
                    
                auction_id = match.group(1)
                item_id = f"publicsurplus_{auction_id}"
                
                if item_id in processed_ids:
                    continue
                processed_ids.add(item_id)
                
                # Título
                title = text
                title = re.sub(r'^#\d+\s*-\s*', '', title)
                
                # Preço - procura no contexto próximo (sobe até a row da tabela)
                price_text = "Consultar no site"
                parent = link_elem
                for _ in range(5):
                    parent = parent.parent
                    if parent is None:
                        break
                    price_match = re.search(r'\$[\d,]+\.?\d*', parent.text)
                    if price_match:
                        price_text = price_match.group(0)
                        break
                
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
                
        return results
