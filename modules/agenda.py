import time
import threading
import logging
import sys
import os
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from modules import database

logger = logging.getLogger('Agenda')


class AgendaManager:
    """
    Gerenciador de agenda e watchlist de leilões.

    Responsabilidades:
    - Monitorar preços dos leilões na watchlist a cada 30 min
    - Enviar alertas quando preço sobe significativamente
    - Enviar alertas quando preço ultrapassa o teto
    - Enviar lembretes: 24h, 1h e 15min antes do encerramento
    - Marcar leilões expirados automaticamente
    """

    PRICE_CHECK_INTERVAL = 1800   # 30 minutos
    REMINDER_CHECK_INTERVAL = 60  # 1 minuto

    def __init__(self, telegram_bot):
        self.bot = telegram_bot
        self.running = False
        self._price_thread = None
        self._reminder_thread = None

    def start(self):
        """Inicia os loops de verificação em threads separadas."""
        if self.running:
            return
        self.running = True

        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self._reminder_thread.start()

        self._price_thread = threading.Thread(target=self._price_loop, daemon=True)
        self._price_thread.start()

        logger.info("AgendaManager iniciado (lembretes + monitoramento de preco).")

    def stop(self):
        self.running = False

    # ------------------------------------------------------------------
    # LOOP DE LEMBRETES (a cada 60s)
    # ------------------------------------------------------------------
    def _reminder_loop(self):
        while self.running:
            try:
                self._check_watchlist_reminders()
                self._check_legacy_reminders()
            except Exception as e:
                logger.error(f"Erro no loop de lembretes: {e}")
            time.sleep(self.REMINDER_CHECK_INTERVAL)

    def _check_watchlist_reminders(self):
        """Verifica lembretes para itens da watchlist."""
        items = database.get_watchlist_items('watching')
        now = datetime.now()

        for item in items:
            try:
                closing = item.get('closing_date')
                if not closing:
                    continue

                if isinstance(closing, str):
                    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            closing = datetime.strptime(closing, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        continue

                diff = closing - now
                sent = (item.get('reminders_sent') or "").split(',')

                # Leilão já encerrou
                if diff.total_seconds() < 0:
                    if item['status'] == 'watching':
                        database.update_watchlist_status(item['id'], 'expired')
                        self._send_expired_alert(item)
                    continue

                # Lembrete de 24h
                if timedelta(hours=23, minutes=55) <= diff <= timedelta(hours=24, minutes=5):
                    if '24h' not in sent:
                        self._send_watchlist_reminder(item, "24 horas")
                        database.update_watchlist_reminders(item['id'], '24h')

                # Lembrete de 1h
                elif timedelta(minutes=55) <= diff <= timedelta(hours=1, minutes=5):
                    if '1h' not in sent:
                        self._send_watchlist_reminder(item, "1 hora")
                        database.update_watchlist_reminders(item['id'], '1h')

                # Lembrete de 15min
                elif timedelta(minutes=10) <= diff <= timedelta(minutes=20):
                    if '15m' not in sent:
                        self._send_watchlist_reminder(item, "15 minutos")
                        database.update_watchlist_reminders(item['id'], '15m')

            except Exception as e:
                logger.error(f"Erro ao processar lembrete watchlist #{item.get('id')}: {e}")

    def _check_legacy_reminders(self):
        """Verifica lembretes da agenda legada."""
        items = database.get_agenda_items()
        now = datetime.now()

        for item in items:
            try:
                auction_date = item.get('auction_date')
                if isinstance(auction_date, str):
                    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
                        try:
                            auction_date = datetime.strptime(auction_date, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        continue

                diff = auction_date - now
                sent = (item.get('reminders_sent') or "").split(',')

                if timedelta(hours=23, minutes=55) <= diff <= timedelta(hours=24, minutes=5):
                    if '24h' not in sent:
                        self.bot.send_reminder(item, "24 horas")
                        database.update_reminders_sent(item['id'], '24h')
                elif timedelta(minutes=55) <= diff <= timedelta(hours=1, minutes=5):
                    if '1h' not in sent:
                        self.bot.send_reminder(item, "1 hora")
                        database.update_reminders_sent(item['id'], '1h')
                elif timedelta(minutes=10) <= diff <= timedelta(minutes=15):
                    if '15m' not in sent:
                        self.bot.send_reminder(item, "15 minutos")
                        database.update_reminders_sent(item['id'], '15m')

            except Exception as e:
                logger.error(f"Erro ao processar lembrete legado #{item.get('id')}: {e}")

    # ------------------------------------------------------------------
    # LOOP DE MONITORAMENTO DE PREÇO (a cada 30 min)
    # ------------------------------------------------------------------
    def _price_loop(self):
        # Espera 2 min após iniciar para não sobrecarregar na inicialização
        time.sleep(120)
        while self.running:
            try:
                self._check_prices()
            except Exception as e:
                logger.error(f"Erro no loop de precos: {e}")
            time.sleep(self.PRICE_CHECK_INTERVAL)

    def _check_prices(self):
        """Verifica preços atuais dos leilões na watchlist."""
        items = database.get_watchlist_items('watching')
        if not items:
            return

        logger.info(f"Verificando precos de {len(items)} itens na watchlist...")

        for item in items:
            try:
                url = item.get('url', '')
                if not url:
                    continue

                new_price = self._fetch_current_price(url)
                if new_price is None:
                    continue

                old_price = item.get('current_price', 0) or 0
                ceiling = item.get('max_price_ceiling', 0) or 0

                # Atualiza o preço no banco
                database.update_watchlist_price(item['id'], new_price)

                # Alerta se preço subiu significativamente (>10%)
                if old_price > 0 and new_price > old_price * 1.10:
                    self._send_price_increase_alert(item, old_price, new_price)

                # Alerta se preço ultrapassou o teto
                if ceiling > 0 and new_price > ceiling and (old_price <= ceiling or old_price == 0):
                    self._send_ceiling_exceeded_alert(item, new_price)

                # Delay entre requisições
                time.sleep(3)

            except Exception as e:
                logger.error(f"Erro ao verificar preco do item #{item.get('id')}: {e}")

    def _fetch_current_price(self, url):
        """
        Tenta extrair o preço atual de uma página de leilão.
        Suporta GovDeals, BidSpotter, Public Surplus, JJ Kane, Joseph Finn.
        """
        try:
            headers = config.HEADERS.copy()
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text()

            # Padrões de preço comuns
            patterns = [
                r'Current\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'High\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Current\s*Price[:\s]*\$?([\d,]+\.?\d*)',
                r'Bid\s*Amount[:\s]*\$?([\d,]+\.?\d*)',
                r'Winning\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Starting\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Price[:\s]*\$?([\d,]+\.?\d*)',
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
            logger.debug(f"Erro ao buscar preco de {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # ENVIO DE ALERTAS
    # ------------------------------------------------------------------
    def _send_watchlist_reminder(self, item, time_left):
        """Envia lembrete de leilão na watchlist."""
        if not self.bot or not self.bot.bot:
            return
        try:
            price = item.get('current_price', 0) or 0
            ceiling = item.get('max_price_ceiling', 0) or 0
            msg = (
                f"\u23f0 *LEMBRETE DE LEILAO* \u23f0\n\n"
                f"O leilao encerra em *{time_left}*!\n\n"
                f"\U0001f4e6 *Item:* {item['title']}\n"
                f"\U0001f3e2 *Site:* {item.get('site', 'N/A')}\n"
                f"\U0001f4b0 *Preco Atual:* ${price:,.2f}\n"
                f"\U0001f6a8 *Seu Teto:* ${ceiling:,.2f}\n\n"
                f"\U0001f517 [Acessar Leilao]({item['url']})"
            )
            self.bot.bot.send_message(
                self.bot.chat_id, msg,
                parse_mode='Markdown', disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar lembrete watchlist: {e}")

    def _send_price_increase_alert(self, item, old_price, new_price):
        """Alerta quando o preço sobe significativamente."""
        if not self.bot or not self.bot.bot:
            return
        try:
            increase_pct = ((new_price - old_price) / old_price * 100) if old_price > 0 else 0
            ceiling = item.get('max_price_ceiling', 0) or 0
            msg = (
                f"\U0001f4c8 *PRECO SUBIU* \U0001f4c8\n\n"
                f"\U0001f4e6 *Item:* {item['title']}\n"
                f"\U0001f4b0 *Preco Anterior:* ${old_price:,.2f}\n"
                f"\U0001f4b5 *Preco Atual:* ${new_price:,.2f}\n"
                f"\U0001f4c8 *Aumento:* +{increase_pct:.1f}%\n"
                f"\U0001f6a8 *Seu Teto:* ${ceiling:,.2f}\n\n"
                f"\U0001f517 [Acessar Leilao]({item['url']})"
            )
            self.bot.bot.send_message(
                self.bot.chat_id, msg,
                parse_mode='Markdown', disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de preco: {e}")

    def _send_ceiling_exceeded_alert(self, item, current_price):
        """Alerta quando o preço ultrapassa o teto."""
        if not self.bot or not self.bot.bot:
            return
        try:
            ceiling = item.get('max_price_ceiling', 0) or 0
            msg = (
                f"\U0001f6a8 *ALERTA: TETO ULTRAPASSADO!* \U0001f6a8\n\n"
                f"\U0001f4e6 *Item:* {item['title']}\n"
                f"\U0001f4b5 *Preco Atual:* ${current_price:,.2f}\n"
                f"\U0001f6a8 *Seu Teto:* ${ceiling:,.2f}\n"
                f"\u274c *Acima do teto em:* ${current_price - ceiling:,.2f}\n\n"
                f"Deseja remover da agenda?\n"
                f"/cancelar {item['id']}\n\n"
                f"\U0001f517 [Acessar Leilao]({item['url']})"
            )
            self.bot.bot.send_message(
                self.bot.chat_id, msg,
                parse_mode='Markdown', disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de teto: {e}")

    def _send_expired_alert(self, item):
        """Alerta quando um leilão expirou."""
        if not self.bot or not self.bot.bot:
            return
        try:
            price = item.get('current_price', 0) or 0
            msg = (
                f"\u23f3 *LEILAO ENCERRADO* \u23f3\n\n"
                f"\U0001f4e6 *Item:* {item['title']}\n"
                f"\U0001f4b0 *Ultimo Preco:* ${price:,.2f}\n"
                f"\U0001f3e2 *Site:* {item.get('site', 'N/A')}\n\n"
                f"Voce arrematou este item?\n"
                f"/ganhou — para registrar a arrematacao\n"
                f"/arquivar {item['id']} — para mover ao arquivo"
            )
            self.bot.bot.send_message(
                self.bot.chat_id, msg,
                parse_mode='Markdown', disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de expiracao: {e}")
