from .base_scraper import BaseScraper, logger
from .auction_utils import should_include_item
import re
from datetime import datetime

class AVGearScraper(BaseScraper):
    """
    Scraper para AVGear Auctions.
    
    AVGear (https://www.avgear.com) é uma loja de equipamentos de áudio e vídeo,
    mas ocasionalmente realiza LEILÕES através de parceiros como Joseph Finn Auctions.
    
    Este scraper monitora APENAS a página de leilões (https://www.avgear.com/pages/auctions)
    e detecta quando há leilões ativos. Quando um leilão está aberto, extrai os links
    para as plataformas de leilão (Joseph Finn, HiBid, etc.) e busca os itens disponíveis.
    
    Estratégia:
    1. Acessa /pages/auctions para verificar status dos leilões
    2. Detecta se há leilão ativo (procura por "Auction Live", "Bidding Open", etc.)
    3. Extrai links para plataformas externas (josephfinn.com, hibid.com, etc.)
    4. Segue os links e extrai itens do leilão
    5. Retorna lista vazia se não houver leilão ativo
    """
    
    def __init__(self):
        super().__init__("AVGear Auctions")
        self.base_url = "https://www.avgear.com"
        self.auctions_page = f"{self.base_url}/pages/auctions"
        
    def search(self, keyword):
        """
        Busca itens em leilões AVGear.
        
        Se não houver leilão ativo, retorna lista vazia.
        Se houver leilão ativo, busca itens que correspondam à keyword.
        """
        logger.info(f"Buscando '{keyword}' em leiloes AVGear...")
        
        # Verifica se há leilão ativo
        auction_status = self._check_auction_status()
        
        if not auction_status["is_active"]:
            logger.info(f"Nenhum leilao ativo no AVGear. Status: {auction_status.get('message', 'Desconhecido')}")
            return []
        
        logger.info(f"Leilao ativo detectado: {auction_status['message']}")
        
        # Se houver leilão ativo, busca os itens
        auction_links = auction_status.get("auction_links", [])
        results = []
        
        for link_info in auction_links:
            link = link_info.get("link", "")
            link_type = link_info.get("type", "")
            
            if not link:
                continue
            
            logger.info(f"Acessando leilao {link_type}: {link}")
            
            try:
                items = self._search_auction_link(link, keyword, link_type)
                results.extend(items)
            except Exception as e:
                logger.error(f"Erro ao buscar em {link}: {e}")
        
        logger.info(f"Encontrados {len(results)} itens ATIVOS no AVGear para '{keyword}'")
        return results
    
    def _check_auction_status(self):
        """
        Verifica se há leilão ativo na página /pages/auctions.
        
        Retorna dict com:
        - is_active: bool (True se leilão está aberto/ativo)
        - message: str (descrição do status)
        - auction_links: list (links para plataformas de leilão)
        """
        try:
            soup = self.fetch_page(self.auctions_page)
            if not soup:
                return {
                    "is_active": False,
                    "message": "Nao conseguiu acessar a pagina de leiloes",
                    "auction_links": []
                }
            
            page_text = soup.get_text().lower()
            
            # Detecta status do leilão
            is_active = False
            message = "Leilao nao encontrado"
            
            if "auction live now" in page_text or "bidding open" in page_text or "bidding is open" in page_text:
                is_active = True
                message = "Leilao ATIVO agora"
            elif "auction opens" in page_text or "next auction opens" in page_text:
                # Tenta extrair data
                date_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})', page_text, re.IGNORECASE)
                if date_match:
                    message = f"Proximo leilao abre em {date_match.group(0).title()}"
                else:
                    message = "Proximo leilao em breve"
                is_active = False
            elif "auction closed" in page_text or "auction ended" in page_text:
                message = "Leilao encerrado"
                is_active = False
            
            # Extrai links para plataformas de leilão
            auction_links = self._extract_auction_links(soup)
            
            # Se encontrou links, considera como potencialmente ativo
            if auction_links and not is_active:
                # Verifica se os links têm indicação de estar aberto
                for link_info in auction_links:
                    link_text = link_info.get("text", "").lower()
                    if "live" in link_text or "open" in link_text or "bidding" in link_text or "catalog" in link_text:
                        is_active = True
                        message = f"Leilao ativo encontrado ({len(auction_links)} links)"
                        break
            
            return {
                "is_active": is_active,
                "message": message,
                "auction_links": auction_links
            }
            
        except Exception as e:
            logger.error(f"Erro ao verificar status do leilao AVGear: {e}")
            return {
                "is_active": False,
                "message": f"Erro: {str(e)}",
                "auction_links": []
            }
    
    def _extract_auction_links(self, soup):
        """
        Extrai links para plataformas de leilão da página.
        
        Procura por links para:
        - josephfinn.com
        - auctions.josephfinn.com
        - hibid.com
        - outros sites de leilão
        """
        links = []
        processed = set()
        
        # Padrões de URLs de leilão
        patterns = [
            r'https?://(?:www\.)?josephfinn\.com/auctions/[^\s"\'<>]+',
            r'https?://auctions\.josephfinn\.com/auctions/[^\s"\'<>]+',
            r'https?://(?:www\.)?hibid\.com/[^\s"\'<>]+',
            r'https?://(?:www\.)?liveauctioneers\.com/[^\s"\'<>]+',
        ]
        
        # Busca links com padrões
        for pattern in patterns:
            matches = re.findall(pattern, soup.get_text())
            for match in matches:
                if match not in processed:
                    processed.add(match)
                    link_type = "Joseph Finn" if "josephfinn" in match else "HiBid" if "hibid" in match else "LiveAuctioneers"
                    links.append({
                        "link": match,
                        "type": link_type,
                        "text": match
                    })
        
        # Busca também em atributos href
        for link_elem in soup.find_all('a', href=True):
            href = link_elem.get('href', '')
            text = link_elem.text.strip()
            
            # Verifica se é link de leilão
            if any(domain in href for domain in ['josephfinn.com', 'hibid.com', 'liveauctioneers.com']):
                if href not in processed:
                    processed.add(href)
                    link_type = "Joseph Finn" if "josephfinn" in href else "HiBid" if "hibid" in href else "LiveAuctioneers"
                    links.append({
                        "link": href,
                        "type": link_type,
                        "text": text or href
                    })
        
        return links
    
    def _search_auction_link(self, link, keyword, link_type):
        """
        Busca itens em um link de leilão externo (Joseph Finn, HiBid, etc.).
        """
        results = []
        
        try:
            soup = self.fetch_page(link)
            if not soup:
                return results
            
            # Procura por itens que correspondam à keyword
            # Diferentes plataformas têm estruturas diferentes
            
            if "josephfinn" in link:
                results = self._search_josephfinn(soup, keyword, link, link_type)
            elif "hibid" in link:
                results = self._search_hibid(soup, keyword, link, link_type)
            elif "liveauctioneers" in link:
                results = self._search_liveauctioneers(soup, keyword, link, link_type)
            else:
                # Busca genérica
                results = self._search_generic_auction(soup, keyword, link, link_type)
            
            return results
            
        except Exception as e:
            logger.error(f"Erro ao buscar em {link}: {e}")
            return []
    
    def _search_josephfinn(self, soup, keyword, base_link, link_type):
        """Busca itens em leilão Joseph Finn."""
        results = []
        processed = set()
        
        # Joseph Finn usa estrutura de catálogo
        # Procura por itens que contenham a keyword
        
        for link_elem in soup.find_all('a', href=re.compile(r'/lot/|/item/')):
            try:
                href = link_elem.get('href', '')
                title = link_elem.text.strip()
                
                if not title or href in processed or len(title) < 3:
                    continue
                
                # Filtra por keyword
                if keyword.lower() not in title.lower() and keyword.lower() not in href.lower():
                    continue
                
                # Filtra apenas leilões ativos
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, title):
                    logger.debug(f"Item descartado (leilao finalizado): {title}")
                    continue
                
                processed.add(href)
                
                # Busca preço no contexto
                price = self._extract_price(link_elem)
                
                item_id = f"avgear_josephfinn_{hash(href) % 100000}"
                full_link = href if href.startswith('http') else f"https://www.josephfinn.com{href}"
                
                results.append({
                    "id": item_id,
                    "site": f"{self.site_name} ({link_type})",
                    "title": title,
                    "link": full_link,
                    "price": price,
                    "keyword": keyword
                })
            except Exception:
                continue
        
        return results[:30]
    
    def _search_hibid(self, soup, keyword, base_link, link_type):
        """Busca itens em leilão HiBid."""
        results = []
        processed = set()
        
        # HiBid usa estrutura diferente
        for link_elem in soup.find_all('a', href=re.compile(r'/cgi-bin/|/lot/')):
            try:
                href = link_elem.get('href', '')
                title = link_elem.text.strip()
                
                if not title or href in processed or len(title) < 3:
                    continue
                
                if keyword.lower() not in title.lower() and keyword.lower() not in href.lower():
                    continue
                
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, title):
                    continue
                
                processed.add(href)
                price = self._extract_price(link_elem)
                
                item_id = f"avgear_hibid_{hash(href) % 100000}"
                full_link = href if href.startswith('http') else f"https://www.hibid.com{href}"
                
                results.append({
                    "id": item_id,
                    "site": f"{self.site_name} ({link_type})",
                    "title": title,
                    "link": full_link,
                    "price": price,
                    "keyword": keyword
                })
            except Exception:
                continue
        
        return results[:30]
    
    def _search_liveauctioneers(self, soup, keyword, base_link, link_type):
        """Busca itens em leilão LiveAuctioneers."""
        results = []
        processed = set()
        
        for link_elem in soup.find_all('a', href=re.compile(r'/item/|/lot/')):
            try:
                href = link_elem.get('href', '')
                title = link_elem.text.strip()
                
                if not title or href in processed or len(title) < 3:
                    continue
                
                if keyword.lower() not in title.lower() and keyword.lower() not in href.lower():
                    continue
                
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, title):
                    continue
                
                processed.add(href)
                price = self._extract_price(link_elem)
                
                item_id = f"avgear_liveauctioneers_{hash(href) % 100000}"
                full_link = href if href.startswith('http') else f"https://www.liveauctioneers.com{href}"
                
                results.append({
                    "id": item_id,
                    "site": f"{self.site_name} ({link_type})",
                    "title": title,
                    "link": full_link,
                    "price": price,
                    "keyword": keyword
                })
            except Exception:
                continue
        
        return results[:30]
    
    def _search_generic_auction(self, soup, keyword, base_link, link_type):
        """Busca genérica em plataforma de leilão desconhecida."""
        results = []
        processed = set()
        
        # Busca por padrões comuns de leilão
        for link_elem in soup.find_all('a', href=True):
            try:
                href = link_elem.get('href', '')
                title = link_elem.text.strip()
                
                if not title or href in processed or len(title) < 3:
                    continue
                
                # Filtra por keyword
                if keyword.lower() not in title.lower() and keyword.lower() not in href.lower():
                    continue
                
                # Ignora links de navegação
                if any(x in href.lower() for x in ['#', 'javascript:', 'login', 'register', 'cart']):
                    continue
                
                element_context = link_elem.parent.get_text() if link_elem.parent else ""
                if not should_include_item(element_context, title):
                    continue
                
                processed.add(href)
                price = self._extract_price(link_elem)
                
                item_id = f"avgear_auction_{hash(href) % 100000}"
                full_link = href if href.startswith('http') else f"{base_link.split('?')[0]}{href}"
                
                results.append({
                    "id": item_id,
                    "site": f"{self.site_name} ({link_type})",
                    "title": title,
                    "link": full_link,
                    "price": price,
                    "keyword": keyword
                })
            except Exception:
                continue
        
        return results[:30]
    
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
