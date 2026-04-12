from .base_scraper import BaseScraper, logger
from .relevance_filter import filter_items
import re

class GovDealsScraper(BaseScraper):
    """
    Scraper para GovDeals.
    Site usa SPA Angular com protecao Akamai - muito dificil de scraper.
    Tenta multiplas estrategias como fallback.
    """
    
    def __init__(self):
        super().__init__("GovDeals")
        self.base_url = "https://www.govdeals.com"

    def search(self, keyword):
        """Busca itens no GovDeals (site SPA Angular com protecao Akamai)."""
        logger.info(f"[GovDeals] Iniciando busca por '{keyword}'")
        
        # Estrategia 1: API (pode estar bloqueada por Akamai)
        logger.debug(f"[GovDeals] Tentando estrategia 1: API")
        results = self._search_api(keyword)
        if results:
            logger.info(f"[GovDeals] API retornou {len(results)} resultados")
            return results
        logger.debug(f"[GovDeals] API falhou ou retornou vazio")
        
        # Estrategia 2: AllSurplus (fallback)
        logger.debug(f"[GovDeals] Tentando estrategia 2: AllSurplus")
        results = self._search_allsurplus(keyword)
        if results:
            logger.info(f"[GovDeals] AllSurplus retornou {len(results)} resultados")
            return results
        logger.debug(f"[GovDeals] AllSurplus falhou ou retornou vazio")
        
        # Estrategia 3: CFM (fallback)
        logger.debug(f"[GovDeals] Tentando estrategia 3: CFM")
        results = self._search_cfm(keyword)
        if results:
            logger.info(f"[GovDeals] CFM retornou {len(results)} resultados")
            return results
        logger.debug(f"[GovDeals] CFM falhou ou retornou vazio")
        
        logger.warning(f"[GovDeals] Nenhum resultado encontrado para '{keyword}' (site usa SPA Angular com Akamai)")
        return []
    
    def _search_api(self, keyword):
        """Tenta buscar via API interna do GovDeals com headers Angular."""
        try:
            api_url = f"{self.base_url}/api/search/assets"
            headers = {
                **self.session.headers,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json",
            }
            params = {
                "keyword": keyword,
                "page": 1,
                "pageSize": 25,
                "sort": "closing_soon"
            }
            
            try:
                response = self.session.get(api_url, params=params, timeout=8, headers=headers)
                if response.status_code == 200:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        data = response.json()
                        logger.debug(f"[GovDeals] API GET retornou JSON")
                        return self._parse_api_results(data, keyword)
                    else:
                        logger.debug(f"[GovDeals] API GET retornou {response.status_code}, content-type: {ct}")
                else:
                    logger.debug(f"[GovDeals] API GET retornou {response.status_code}")
            except Exception as e:
                logger.debug(f"[GovDeals] API GET erro: {e}")
            
            # Tentar POST
            payload = {
                "keyword": keyword,
                "page": 1,
                "pageSize": 25,
                "sort": "closing_soon"
            }
            response = self.session.post(api_url, json=payload, timeout=8, headers=headers)
            if response.status_code == 200:
                ct = response.headers.get('content-type', '')
                if 'json' in ct:
                    data = response.json()
                    logger.debug(f"[GovDeals] API POST retornou JSON")
                    return self._parse_api_results(data, keyword)
                else:
                    logger.debug(f"[GovDeals] API POST retornou {response.status_code}, content-type: {ct}")
            else:
                logger.debug(f"[GovDeals] API POST retornou {response.status_code}")
        except Exception as e:
            logger.debug(f"[GovDeals] API erro geral: {e}")
        
        return []
    
    def _parse_api_results(self, data, keyword):
        """Parse resultados da API."""
        results = []
        try:
            items = data.get('items', []) or data.get('data', []) or []
            for item in items:
                try:
                    title = item.get('title', '') or item.get('name', '')
                    link = item.get('link', '') or item.get('url', '')
                    price = item.get('price', '') or item.get('current_bid', '')
                    
                    if not title or not link:
                        continue
                    
                    results.append({
                        "id": f"govdeals_{item.get('id', hash(title) % 100000)}",
                        "site": self.site_name,
                        "title": title,
                        "link": link if link.startswith('http') else f"{self.base_url}{link}",
                        "price": price,
                        "keyword": keyword
                    })
                except Exception:
                    continue
            
            if results:
                results = filter_items(results, keyword, min_score=0.5)
        except Exception as e:
            logger.debug(f"[GovDeals] Parse API erro: {e}")
        
        return results
    
    def _search_allsurplus(self, keyword):
        """Tenta buscar no AllSurplus (fallback)."""
        try:
            url = "https://www.allsurplus.com/search"
            params = {"q": keyword}
            soup = self.fetch_page(url, params=params)
            if not soup:
                logger.debug(f"[GovDeals] AllSurplus: fetch_page retornou None")
                return []
            
            results = []
            for link in soup.find_all('a', href=True):
                try:
                    href = link['href']
                    title = link.get_text(strip=True)
                    if keyword.lower() not in title.lower():
                        continue
                    if not title or len(title) < 5:
                        continue
                    
                    results.append({
                        "id": f"govdeals_allsurplus_{hash(href) % 100000}",
                        "site": f"{self.site_name} (AllSurplus)",
                        "title": title,
                        "link": href if href.startswith('http') else f"https://www.allsurplus.com{href}",
                        "price": "Consultar",
                        "keyword": keyword
                    })
                except Exception:
                    continue
            
            if results:
                results = filter_items(results, keyword, min_score=0.5)
            return results
        except Exception as e:
            logger.debug(f"[GovDeals] AllSurplus erro: {e}")
            return []
    
    def _search_cfm(self, keyword):
        """Tenta buscar no CFM (fallback)."""
        try:
            url = "https://www.cfmauctionservices.com/search"
            params = {"q": keyword}
            soup = self.fetch_page(url, params=params)
            if not soup:
                logger.debug(f"[GovDeals] CFM: fetch_page retornou None")
                return []
            
            results = []
            for link in soup.find_all('a', href=True):
                try:
                    href = link['href']
                    title = link.get_text(strip=True)
                    if keyword.lower() not in title.lower():
                        continue
                    if not title or len(title) < 5:
                        continue
                    
                    results.append({
                        "id": f"govdeals_cfm_{hash(href) % 100000}",
                        "site": f"{self.site_name} (CFM)",
                        "title": title,
                        "link": href if href.startswith('http') else f"https://www.cfmauctionservices.com{href}",
                        "price": "Consultar",
                        "keyword": keyword
                    })
                except Exception:
                    continue
            
            if results:
                results = filter_items(results, keyword, min_score=0.5)
            return results
        except Exception as e:
            logger.debug(f"[GovDeals] CFM erro: {e}")
            return []
