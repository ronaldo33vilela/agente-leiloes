import time
import threading
import logging
import sys
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from modules import database

logger = logging.getLogger('PostAuction')


class PostAuctionManager:
    """
    Gerenciador de pos-arrematacao e coleta de precos historicos.

    Responsabilidades:
    - Coletar preco final de leiloes encerrados (watchlist expirados)
    - Salvar precos finais no historico para referencia futura
    - Verificar status de itens em transito
    - Comparar novos leiloes com historico de precos
    """

    CHECK_INTERVAL = 21600  # 6 horas

    def __init__(self, telegram_bot):
        self.bot = telegram_bot
        self.running = False
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("PostAuctionManager iniciado.")

    def stop(self):
        self.running = False

    def _check_loop(self):
        time.sleep(300)
        while self.running:
            try:
                self._collect_final_prices()
                self._check_tracking()
            except Exception as e:
                logger.error(f"Erro no loop de pos-arrematacao: {e}")
            time.sleep(self.CHECK_INTERVAL)

    # ------------------------------------------------------------------
    # COLETA DE PRECOS FINAIS
    # ------------------------------------------------------------------
    def _collect_final_prices(self):
        """Coleta o preco final de leiloes expirados da watchlist."""
        expired_items = database.get_watchlist_items('expired')
        if not expired_items:
            return

        logger.info(f"Coletando precos finais de {len(expired_items)} leiloes expirados...")

        for item in expired_items:
            try:
                url = item.get('url', '')
                if not url:
                    self._save_to_history(item, item.get('current_price', 0))
                    database.update_watchlist_status(item['id'], 'history_collected')
                    continue

                final_price = self._fetch_final_price(url)
                if final_price is None:
                    final_price = item.get('current_price', 0) or 0

                self._save_to_history(item, final_price)
                database.update_watchlist_status(item['id'], 'history_collected')
                logger.info(f"Preco final coletado: {item['title']} = ${final_price:,.2f}")
                time.sleep(3)

            except Exception as e:
                logger.error(f"Erro ao coletar preco final do item #{item.get('id')}: {e}")

    def _fetch_final_price(self, url):
        """Tenta extrair o preco final de uma pagina de leilao encerrado."""
        try:
            headers = config.HEADERS.copy()
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text()

            patterns = [
                r'(?:Final|Winning|Sold|Hammer)\s*(?:Bid|Price)[:\s]*\$?([\d,]+\.?\d*)',
                r'(?:Sold|Awarded)\s*(?:for|at|:)\s*\$?([\d,]+\.?\d*)',
                r'Current\s*(?:Bid|Price)[:\s]*\$?([\d,]+\.?\d*)',
                r'High\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Bid\s*Amount[:\s]*\$?([\d,]+\.?\d*)',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    price_str = match.group(1).replace(',', '')
                    price = float(price_str)
                    if price > 0:
                        return price

            return None
        except Exception as e:
            logger.debug(f"Erro ao buscar preco final de {url}: {e}")
            return None

    def _save_to_history(self, item, final_price):
        """Salva um leilao no historico de precos."""
        database.add_price_history(
            title=item.get('title', 'N/A'),
            category=item.get('category', ''),
            final_price=final_price,
            closing_date=item.get('closing_date'),
            site=item.get('site', ''),
            url=item.get('url', ''),
            participated=False,
            won=False
        )

    # ------------------------------------------------------------------
    # COLETA DE PRECOS DE ITENS NOTIFICADOS
    # ------------------------------------------------------------------
    def collect_notified_item_price(self, item_data):
        """Registra o preco de um item notificado no historico."""
        try:
            price_str = str(item_data.get('price', '0'))
            price = 0.0
            match = re.search(r'[\d,]+\.?\d*', price_str.replace(',', ''))
            if match:
                price = float(match.group(0))

            database.add_price_history(
                title=item_data.get('title', 'N/A'),
                category=item_data.get('keyword', ''),
                final_price=price,
                closing_date=datetime.now(),
                site=item_data.get('site', ''),
                url=item_data.get('link', ''),
                participated=False,
                won=False
            )
        except Exception as e:
            logger.debug(f"Erro ao registrar preco no historico: {e}")

    # ------------------------------------------------------------------
    # COMPARACAO COM HISTORICO
    # ------------------------------------------------------------------
    def compare_with_history(self, title, current_price):
        """
        Compara um item com o historico de precos e retorna analise.
        Retorna string com a comparacao ou None se nao houver dados.
        """
        try:
            keywords = title.split()[:3]
            search_term = ' '.join(keywords)

            avg_data = database.get_average_price(search_term)
            last_auction = database.get_last_similar_auction(search_term)

            if not avg_data and not last_auction:
                return None

            analysis = ""

            if avg_data and avg_data['total_records'] > 0:
                avg = avg_data['avg_price']
                if current_price > 0 and avg > 0:
                    margin = ((avg - current_price) / avg) * 100
                    analysis += (
                        f"\U0001f4ca *Historico de Precos:*\n"
                        f"  Preco medio: ${avg:,.2f} ({avg_data['total_records']} leiloes)\n"
                        f"  Faixa: ${avg_data['min_price']:,.2f} - ${avg_data['max_price']:,.2f}\n"
                        f"  Margem potencial: {margin:.0f}%\n"
                    )

            if last_auction:
                last_price = last_auction.get('final_price', 0)
                last_date = last_auction.get('closing_date', 'N/A')
                if isinstance(last_date, str) and len(last_date) > 10:
                    last_date = last_date[:10]
                analysis += f"  Ultimo similar: ${last_price:,.2f} em {last_date}\n"

            return analysis if analysis else None

        except Exception as e:
            logger.debug(f"Erro ao comparar com historico: {e}")
            return None

    # ------------------------------------------------------------------
    # VERIFICACAO DE RASTREIO
    # ------------------------------------------------------------------
    def _check_tracking(self):
        """Verifica status de itens em transito."""
        items = database.get_transit_items()
        if not items:
            return
        logger.info(f"Verificando rastreio de {len(items)} itens em transito...")
        for item in items:
            try:
                tracking = item.get('tracking_number', '')
                if tracking:
                    logger.info(f"Rastreio {tracking}: verificacao automatica pendente")
            except Exception as e:
                logger.error(f"Erro ao verificar rastreio do item #{item.get('id')}: {e}")

    def get_freight_quotes(self, origin_zip, dest_zip, weight, dimensions):
        """Exemplo de cotacoes de frete (simulacao)."""
        return [
            {"carrier": "FedEx Freight", "price": 150.00, "days": "3-5 dias"},
            {"carrier": "UPS Freight", "price": 165.00, "days": "2-4 dias"},
            {"carrier": "uShip Independent", "price": 120.00, "days": "5-7 dias"}
        ]
