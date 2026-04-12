import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import sys
import os
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from modules import database

logger = logging.getLogger('TelegramBot')


class AuctionTelegramBot:
    """Modulo para gerenciar a comunicacao com o Telegram."""

    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID

        if not self.token or self.token == "SEU_TOKEN_AQUI":
            logger.warning("TELEGRAM_TOKEN nao configurado. O bot nao funcionara.")
            self.bot = None
        else:
            self.bot = telebot.TeleBot(self.token)
            self._setup_handlers()

    def _check_auth(self, message):
        return str(message.chat.id) == str(self.chat_id)

    def _setup_handlers(self):
        """Configura todos os comandos do bot."""

        # ==========================================
        # /start e /help
        # ==========================================
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            if not self._check_auth(message):
                self.bot.reply_to(message, "Acesso negado. Este bot e privado.")
                return

            help_text = (
                "\U0001f916 *Agente de Leiloes R33*\n\n"
                "*Comandos Disponiveis:*\n\n"
                "*Monitoramento:*\n"
                "/buscar [termo] - Busca manual nos sites\n\n"
                "*Agenda / Watchlist:*\n"
                "/agendar URL TETO - Adiciona leilao a agenda com preco teto\n"
                "/agenda - Lista leiloes na agenda com preco atual\n"
                "/teto ID VALOR - Altera o teto de um leilao\n"
                "/cancelar ID - Remove um leilao da agenda\n\n"
                "*Arquivo:*\n"
                "/arquivar ID - Move leilao para arquivo\n"
                "/arquivo [categoria] - Lista arquivo de uma categoria\n\n"
                "*Historico de Precos:*\n"
                "/historico PRODUTO - Historico de precos de um produto\n"
                "/preco PRODUTO - Preco medio de arrematacao\n\n"
                "*Pos-Arrematacao:*\n"
                "/ganhou - Registra um lote arrematado\n"
                "/frete ID | Transp | Rastreio - Registra frete\n"
                "/rastrear - Status de itens em transito\n"
                "/entregue ID - Marca item como entregue\n\n"
                "*Estoque e Vendas:*\n"
                "/estoque - Lista itens disponiveis\n"
                "/vender ID Valor - Marca item como vendido\n"
                "/dashboard - Resumo completo\n"
            )
            self.bot.reply_to(message, help_text, parse_mode='Markdown')

        # ==========================================
        # /agendar URL TETO
        # ==========================================
        @self.bot.message_handler(commands=['agendar'])
        def agendar_leilao(message):
            if not self._check_auth(message):
                return

            parts = message.text.split()
            if len(parts) >= 3:
                # Formato direto: /agendar URL TETO
                url = parts[1]
                try:
                    ceiling = float(parts[2].replace('$', '').replace(',', ''))
                except ValueError:
                    self.bot.reply_to(message, "\u274c Valor do teto invalido. Use: /agendar URL TETO\nExemplo: /agendar https://govdeals.com/item/123 3000")
                    return

                # Detecta o site pela URL
                site = self._detect_site(url)

                # Tenta extrair titulo e preco da pagina
                title, current_price = self._fetch_item_info(url)
                if not title:
                    title = f"Leilao {site}"

                # Tenta extrair closing date (pode nao conseguir)
                closing_date = None

                item_id = database.add_to_watchlist(
                    title=title,
                    url=url,
                    site=site,
                    category=self._detect_category(title),
                    current_price=current_price or 0,
                    max_price_ceiling=ceiling,
                    closing_date=closing_date
                )

                response = (
                    f"\u2705 Leilao adicionado a agenda! (ID: {item_id})\n\n"
                    f"\U0001f4e6 *Item:* {title}\n"
                    f"\U0001f3e2 *Site:* {site}\n"
                    f"\U0001f4b0 *Preco Atual:* ${current_price:,.2f}\n"
                    f"\U0001f6a8 *Teto:* ${ceiling:,.2f}\n\n"
                    f"O agente monitorara o preco a cada 30 min.\n"
                    f"Voce recebera alertas de preco e lembretes."
                )
                self.bot.reply_to(message, response, parse_mode='Markdown')
            else:
                # Formato antigo interativo
                msg = self.bot.reply_to(
                    message,
                    "\U0001f4c5 Para agendar um leilao, use:\n\n"
                    "*Formato rapido:*\n"
                    "`/agendar URL TETO`\n"
                    "Exemplo: `/agendar https://govdeals.com/item/123 3000`\n\n"
                    "*Ou responda com formato completo:*\n"
                    "`Data (DD/MM/AAAA HH:MM) | Lance Minimo | Titulo | Site | Link`",
                    parse_mode='Markdown'
                )
                self.bot.register_next_step_handler(msg, self._process_agenda)

        # ==========================================
        # /agenda
        # ==========================================
        @self.bot.message_handler(commands=['agenda'])
        def list_agenda(message):
            if not self._check_auth(message):
                return

            items = database.get_watchlist_items('watching')
            if not items:
                self.bot.reply_to(message, "\U0001f4c5 Sua agenda esta vazia.\nUse /agendar URL TETO para adicionar.")
                return

            response = "\U0001f4c5 *LEILOES NA AGENDA*\n\n"
            for item in items:
                price = item.get('current_price', 0) or 0
                ceiling = item.get('max_price_ceiling', 0) or 0
                status_emoji = "\U0001f7e2" if price <= ceiling else "\U0001f534"

                response += f"\U0001f194 *ID:* {item['id']}\n"
                response += f"\U0001f4e6 *Item:* {item['title']}\n"
                response += f"\U0001f3e2 *Site:* {item.get('site', 'N/A')}\n"
                response += f"\U0001f4b0 *Preco Atual:* ${price:,.2f}\n"
                response += f"\U0001f6a8 *Teto:* ${ceiling:,.2f} {status_emoji}\n"

                closing = item.get('closing_date')
                if closing:
                    response += f"\u23f0 *Encerra:* {str(closing)[:16]}\n"

                response += f"\U0001f517 [Ver Leilao]({item['url']})\n"
                response += "------------------------\n"

            self.bot.reply_to(message, response, parse_mode='Markdown', disable_web_page_preview=True)

        # ==========================================
        # /teto ID VALOR
        # ==========================================
        @self.bot.message_handler(commands=['teto'])
        def update_ceiling(message):
            if not self._check_auth(message):
                return
            try:
                parts = message.text.split()
                item_id = int(parts[1])
                new_ceiling = float(parts[2].replace('$', '').replace(',', ''))

                if database.update_watchlist_ceiling(item_id, new_ceiling):
                    self.bot.reply_to(message, f"\u2705 Teto do item {item_id} atualizado para ${new_ceiling:,.2f}")
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado na agenda.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "\u274c Formato incorreto. Use: /teto ID VALOR\nExemplo: /teto 5 3000")

        # ==========================================
        # /cancelar ID
        # ==========================================
        @self.bot.message_handler(commands=['cancelar'])
        def cancel_item(message):
            if not self._check_auth(message):
                return
            try:
                item_id = int(message.text.split()[1])
                # Tenta remover da watchlist primeiro, depois da agenda legada
                if database.remove_from_watchlist(item_id):
                    self.bot.reply_to(message, f"\u2705 Item {item_id} removido da agenda.")
                elif database.remove_from_agenda(item_id):
                    self.bot.reply_to(message, f"\u2705 Item {item_id} removido da agenda.")
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "\u274c Formato incorreto. Use: /cancelar ID")

        # ==========================================
        # /arquivar ID
        # ==========================================
        @self.bot.message_handler(commands=['arquivar'])
        def archive_item(message):
            if not self._check_auth(message):
                return
            try:
                item_id = int(message.text.split()[1])
                if database.archive_watchlist_item(item_id):
                    self.bot.reply_to(message, f"\U0001f4c1 Item {item_id} movido para o arquivo.")
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "\u274c Formato incorreto. Use: /arquivar ID")

        # ==========================================
        # /arquivo [categoria]
        # ==========================================
        @self.bot.message_handler(commands=['arquivo'])
        def list_archive(message):
            if not self._check_auth(message):
                return

            parts = message.text.split(maxsplit=1)
            category = parts[1].strip() if len(parts) > 1 else None

            items = database.get_archived_items(category)
            if not items:
                if category:
                    self.bot.reply_to(message, f"\U0001f4c1 Nenhum item arquivado na categoria '{category}'.")
                else:
                    self.bot.reply_to(message, "\U0001f4c1 Arquivo vazio.")
                return

            response = f"\U0001f4c1 *ARQUIVO"
            if category:
                response += f" - {category.upper()}"
            response += f"* ({len(items)} itens)\n\n"

            for item in items[:20]:  # Limita a 20 para nao estourar mensagem
                price = item.get('current_price', 0) or 0
                response += f"\U0001f194 {item['id']} | {item['title'][:40]}\n"
                response += f"   ${price:,.2f} | {item.get('site', 'N/A')}\n"
                response += f"   Cat: {item.get('category', 'N/A')}\n\n"

            if len(items) > 20:
                response += f"... e mais {len(items) - 20} itens."

            self.bot.reply_to(message, response, parse_mode='Markdown', disable_web_page_preview=True)

        # ==========================================
        # /historico PRODUTO
        # ==========================================
        @self.bot.message_handler(commands=['historico'])
        def show_history(message):
            if not self._check_auth(message):
                return

            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                self.bot.reply_to(message, "\u274c Use: /historico PRODUTO\nExemplo: /historico Yamaha CL5")
                return

            search_term = parts[1].strip()
            items = database.search_price_history(search_term, limit=15)

            if not items:
                self.bot.reply_to(message, f"\U0001f4ca Nenhum historico encontrado para '{search_term}'.")
                return

            response = f"\U0001f4ca *HISTORICO DE PRECOS: {search_term}*\n\n"
            for item in items:
                price = item.get('final_price', 0) or 0
                date = str(item.get('closing_date', 'N/A'))[:10]
                site = item.get('site', 'N/A')
                participated = "\u2705" if item.get('participated') else ""
                won = "\U0001f3c6" if item.get('won') else ""

                response += f"${price:,.2f} | {date} | {site} {participated}{won}\n"
                response += f"  {item['title'][:50]}\n\n"

            # Adiciona estatisticas
            avg_data = database.get_average_price(search_term)
            if avg_data:
                response += f"\n*Estatisticas ({avg_data['total_records']} leiloes):*\n"
                response += f"  Media: ${avg_data['avg_price']:,.2f}\n"
                response += f"  Min: ${avg_data['min_price']:,.2f}\n"
                response += f"  Max: ${avg_data['max_price']:,.2f}\n"

            self.bot.reply_to(message, response, parse_mode='Markdown', disable_web_page_preview=True)

        # ==========================================
        # /preco PRODUTO
        # ==========================================
        @self.bot.message_handler(commands=['preco'])
        def show_average_price(message):
            if not self._check_auth(message):
                return

            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                self.bot.reply_to(message, "\u274c Use: /preco PRODUTO\nExemplo: /preco Allen Heath SQ5")
                return

            search_term = parts[1].strip()
            avg_data = database.get_average_price(search_term)
            last = database.get_last_similar_auction(search_term)

            if not avg_data:
                self.bot.reply_to(message, f"\U0001f4b0 Nenhum dado de preco para '{search_term}'.")
                return

            response = f"\U0001f4b0 *PRECO MEDIO: {search_term}*\n\n"
            response += f"\U0001f4ca *{avg_data['total_records']} leiloes analisados*\n\n"
            response += f"\U0001f4b5 *Preco Medio:* ${avg_data['avg_price']:,.2f}\n"
            response += f"\U0001f53d *Minimo:* ${avg_data['min_price']:,.2f}\n"
            response += f"\U0001f53c *Maximo:* ${avg_data['max_price']:,.2f}\n"

            if last:
                last_price = last.get('final_price', 0) or 0
                last_date = str(last.get('closing_date', 'N/A'))[:10]
                last_site = last.get('site', 'N/A')
                response += f"\n*Ultimo leilao:*\n"
                response += f"  ${last_price:,.2f} em {last_date} ({last_site})\n"
                response += f"  {last['title'][:60]}\n"

            self.bot.reply_to(message, response, parse_mode='Markdown', disable_web_page_preview=True)

        # ==========================================
        # /ganhou
        # ==========================================
        @self.bot.message_handler(commands=['ganhou'])
        def register_win(message):
            if not self._check_auth(message):
                return
            msg = self.bot.reply_to(
                message,
                "\U0001f389 Parabens pela arrematacao!\n\n"
                "Responda com os dados no formato:\n"
                "`Nome do Item | Site | Valor Pago | Localizacao`\n\n"
                "Exemplo:\n"
                "`Golf Cart EZGO | GovDeals | 1500.00 | Miami, FL`",
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(msg, self._process_win)

        # ==========================================
        # /frete
        # ==========================================
        @self.bot.message_handler(commands=['frete'])
        def register_freight(message):
            if not self._check_auth(message):
                return
            try:
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    raise ValueError("Parametros insuficientes")
                data_parts = [p.strip() for p in parts[1].split('|')]
                if len(data_parts) != 3:
                    raise ValueError("Formato incorreto")
                item_id = int(data_parts[0])
                carrier = data_parts[1]
                tracking_number = data_parts[2]
                if database.update_shipping(item_id, carrier, tracking_number):
                    self.bot.reply_to(
                        message,
                        f"\u2705 Frete registrado!\n\n"
                        f"\U0001f4e6 *Item ID:* {item_id}\n"
                        f"\U0001f69a *Transportadora:* {carrier}\n"
                        f"\U0001f522 *Rastreio:* `{tracking_number}`",
                        parse_mode='Markdown'
                    )
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado.")
            except (ValueError, IndexError):
                self.bot.reply_to(
                    message,
                    "\u274c Formato incorreto. Use:\n"
                    "`/frete ID | Transportadora | CodigoRastreio`\n"
                    "Exemplo: `/frete 1 | FedEx | 123456789012`",
                    parse_mode='Markdown'
                )

        # ==========================================
        # /rastrear
        # ==========================================
        @self.bot.message_handler(commands=['rastrear'])
        def track_items(message):
            if not self._check_auth(message):
                return
            items = database.get_transit_items()
            if not items:
                self.bot.reply_to(message, "\U0001f69a Nao ha itens em transito.")
                return
            response = "\U0001f69a *ITENS EM TRANSITO*\n\n"
            for item in items:
                response += f"\U0001f194 *ID:* {item['id']}\n"
                response += f"\U0001f4e6 *Item:* {item['title']}\n"
                response += f"\U0001f3e2 *Transportadora:* {item.get('carrier', 'N/A')}\n"
                response += f"\U0001f522 *Rastreio:* `{item.get('tracking_number', 'N/A')}`\n"
                response += f"\U0001f4cd *Status:* {item.get('tracking_status') or 'Aguardando atualizacao'}\n"
                response += "------------------------\n"
            self.bot.reply_to(message, response, parse_mode='Markdown')

        # ==========================================
        # /entregue ID
        # ==========================================
        @self.bot.message_handler(commands=['entregue'])
        def mark_delivered(message):
            if not self._check_auth(message):
                return
            try:
                item_id = int(message.text.split()[1])
                if database.move_to_inventory(item_id, "Item entregue via leilao", 0, "Usado - Ver descricao"):
                    self.bot.reply_to(message, f"\u2705 Item {item_id} entregue e adicionado ao estoque!")
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "\u274c Formato incorreto. Use: /entregue ID")

        # ==========================================
        # /estoque
        # ==========================================
        @self.bot.message_handler(commands=['estoque'])
        def list_inventory(message):
            if not self._check_auth(message):
                return
            items = database.get_inventory()
            if not items:
                self.bot.reply_to(message, "\U0001f4e6 Seu estoque esta vazio.")
                return
            response = "\U0001f4e6 *ESTOQUE DISPONIVEL*\n\n"
            for item in items:
                response += f"\U0001f194 *ID:* {item['id']}\n"
                response += f"\U0001f4e6 *Item:* {item['title']}\n"
                response += f"\U0001f4b0 *Custo:* ${item.get('price_paid', 0):,.2f}\n"
                sp = item.get('suggested_price', 0) or 0
                response += f"\U0001f3f7 *Preco Sugerido:* ${sp:,.2f}\n"
                response += f"\u2b50 *Condicao:* {item.get('condition', 'N/A')}\n"
                response += "------------------------\n"
            self.bot.reply_to(message, response, parse_mode='Markdown')

        # ==========================================
        # /vender ID Valor
        # ==========================================
        @self.bot.message_handler(commands=['vender'])
        def sell_item(message):
            if not self._check_auth(message):
                return
            try:
                parts = message.text.split()
                item_id = int(parts[1])
                sale_price = float(parts[2].replace('$', '').replace(',', ''))
                if database.sell_item(item_id, sale_price):
                    self.bot.reply_to(message, f"\u2705 Item {item_id} vendido por ${sale_price:,.2f}!")
                else:
                    self.bot.reply_to(message, f"\u274c Item {item_id} nao encontrado no estoque.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "\u274c Formato incorreto. Use: /vender ID Valor\nExemplo: /vender 5 2500.00")

        # ==========================================
        # /dashboard (via Telegram)
        # ==========================================
        @self.bot.message_handler(commands=['dashboard'])
        def show_dashboard(message):
            if not self._check_auth(message):
                return
            stats = database.get_dashboard_stats()
            response = "\U0001f4ca *DASHBOARD DE LEILOES*\n\n"
            response += f"\U0001f4c5 *Na Agenda:* {stats.get('watching', 0)}\n"
            response += f"\U0001f4c1 *Arquivados:* {stats.get('archived', 0)}\n"
            response += f"\U0001f69a *Em Transito:* {stats.get('em_transito', 0)}\n"
            response += f"\U0001f4e6 *Em Estoque:* {stats.get('em_estoque', 0)}\n"
            response += f"\U0001f4ca *Historico:* {stats.get('total_historico', 0)} registros\n\n"
            response += f"\U0001f4b8 *Total Investido:* ${stats.get('total_investido', 0):,.2f}\n"
            response += f"\U0001f4c8 *Total em Vendas:* ${stats.get('total_vendas', 0):,.2f}\n"
            lucro = stats.get('lucro_acumulado', 0)
            emoji = "\U0001f7e2" if lucro >= 0 else "\U0001f534"
            response += f"{emoji} *Lucro Acumulado:* ${lucro:,.2f}\n"
            self.bot.reply_to(message, response, parse_mode='Markdown')

        # ==========================================
        # CALLBACK: Botao Agendar (inline)
        # ==========================================
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('agendar_'))
        def callback_agendar(call):
            if str(call.message.chat.id) != str(self.chat_id):
                return
            msg = self.bot.send_message(
                call.message.chat.id,
                "\U0001f4c5 Para agendar, use:\n"
                "`/agendar URL TETO`\n"
                "Exemplo: `/agendar https://govdeals.com/item/123 3000`",
                parse_mode='Markdown'
            )
            self.bot.answer_callback_query(call.id)

    # ==========================================
    # PROCESSADORES DE RESPOSTAS
    # ==========================================
    def _process_win(self, message):
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) != 4:
                raise ValueError("Numero incorreto de parametros (esperado: 4)")
            title, site, price_str, location = parts
            price = float(price_str.replace('$', '').replace(',', ''))
            item_id = database.add_won_item(title, site, price, location)

            # Registra no historico de precos como participou e ganhou
            database.add_price_history(
                title=title, category='', final_price=price,
                closing_date=datetime.now(), site=site, url='',
                participated=True, won=True
            )

            response = (
                f"\u2705 Lote registrado! (ID: {item_id})\n\n"
                f"Para registrar o frete:\n"
                f"`/frete {item_id} | Transportadora | CodigoRastreio`"
            )
            self.bot.reply_to(message, response, parse_mode='Markdown')
        except Exception as e:
            self.bot.reply_to(message, f"\u274c Erro ao processar: {e}\nTente novamente com o formato correto.")

    def _process_agenda(self, message):
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) != 5:
                raise ValueError("Numero incorreto de parametros (esperado: 5)")
            date_str, min_bid_str, title, site, link = parts
            auction_date = datetime.strptime(date_str, '%d/%m/%Y %H:%M')
            min_bid = float(min_bid_str.replace('$', '').replace(',', ''))
            item_id = database.add_to_agenda(title, site, link, auction_date, min_bid)
            self.bot.reply_to(message, f"\u2705 Leilao agendado! (ID: {item_id})\nLembretes: 24h, 1h e 15m antes.")
        except Exception as e:
            self.bot.reply_to(message, f"\u274c Erro ao processar: {e}\nTente novamente com o formato correto.")

    # ==========================================
    # UTILITARIOS
    # ==========================================
    def _detect_site(self, url):
        """Detecta o site de leilao pela URL."""
        url_lower = url.lower()
        if 'govdeals' in url_lower:
            return 'GovDeals'
        elif 'bidspotter' in url_lower:
            return 'BidSpotter'
        elif 'publicsurplus' in url_lower:
            return 'Public Surplus'
        elif 'jjkane' in url_lower:
            return 'JJ Kane'
        elif 'avgear' in url_lower:
            return 'AVGear'
        elif 'hibid' in url_lower:
            return 'HiBid'
        elif 'josephfinn' in url_lower:
            return 'Joseph Finn'
        else:
            return 'Outro'

    def _detect_category(self, title):
        """Tenta detectar a categoria pelo titulo."""
        title_lower = title.lower()
        if any(k in title_lower for k in ['allen', 'heath', 'sq5', 'sq6', 'sq7', 'dlive', 'avantis']):
            return 'allen_heath'
        elif any(k in title_lower for k in ['shure', 'axient', 'ulxd', 'qlxd']):
            return 'shure_axient'
        elif any(k in title_lower for k in ['golf cart', 'ezgo', 'club car', 'yamaha drive']):
            return 'golf_cart'
        elif any(k in title_lower for k in ['led', 'panel', 'video wall']):
            return 'led'
        elif any(k in title_lower for k in ['lighting', 'grandma', 'ma3', 'chamsys', 'etc eos']):
            return 'lighting'
        else:
            return 'other'

    def _fetch_item_info(self, url):
        """Tenta extrair titulo e preco atual de uma pagina de leilao."""
        try:
            import requests
            from bs4 import BeautifulSoup

            headers = config.HEADERS.copy()
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None, 0

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Titulo
            title = None
            for tag in ['h1', 'h2', 'title']:
                elem = soup.find(tag)
                if elem and elem.get_text(strip=True):
                    title = elem.get_text(strip=True)[:100]
                    break

            # Preco
            text = soup.get_text()
            price = 0.0
            patterns = [
                r'Current\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'High\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Starting\s*Bid[:\s]*\$?([\d,]+\.?\d*)',
                r'Price[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    price = float(match.group(1).replace(',', ''))
                    if price > 0:
                        break

            return title, price

        except Exception as e:
            logger.debug(f"Erro ao buscar info de {url}: {e}")
            return None, 0

    # ==========================================
    # COMANDO /buscar
    # ==========================================
    def handle_search_command(self, search_term):
        """
        Busca um termo em TODAS as 5 plataformas e retorna resultados.
        Retorna lista de dicts com: title, site, link, price, relevance_score
        """
        if not search_term or len(search_term.strip()) == 0:
            return None, "Uso: /buscar TERMO\nExemplo: /buscar golf cart"
        
        try:
            from scrapers.govdeals import GovDealsScraper
            from scrapers.bidspotter import BidSpotterScraper
            from scrapers.publicsurplus import PublicSurplusScraper
            from scrapers.jjkane import JJKaneScraper
            from scrapers.avgear import AVGearScraper
            from scrapers.relevance_filter import filter_items
            
            all_results = []
            
            # Busca em cada plataforma
            scrapers = [
                (GovDealsScraper(), 'GovDeals'),
                (BidSpotterScraper(), 'BidSpotter'),
                (PublicSurplusScraper(), 'Public Surplus'),
                (JJKaneScraper(), 'JJ Kane'),
                (AVGearScraper(), 'AVGear'),
            ]
            
            logger.info(f"Iniciando busca por: {search_term}")
            
            for scraper, site_name in scrapers:
                try:
                    logger.debug(f"Buscando em {site_name}...")
                    results = scraper.search(search_term)
                    if results:
                        all_results.extend(results)
                        logger.debug(f"{site_name}: {len(results)} resultados encontrados")
                except Exception as e:
                    logger.warning(f"Erro ao buscar em {site_name}: {e}")
                    continue
            
            if not all_results:
                return None, f"Nenhum resultado encontrado para: <b>{search_term}</b>"
            
            # Aplica filtro de relevância novamente para garantir qualidade
            filtered = filter_items(all_results, search_term, min_score=0.5)
            
            if not filtered:
                return None, f"Nenhum resultado relevante encontrado para: <b>{search_term}</b>"
            
            # Limita a 10 resultados para nao estourar tamanho de mensagem
            filtered = filtered[:10]
            
            logger.info(f"Busca concluida: {len(filtered)} resultados relevantes")
            return filtered, None
            
        except Exception as e:
            logger.error(f"Erro ao executar busca: {e}")
            return None, f"Erro ao executar busca: {str(e)}"

    # ==========================================
    # METODOS DE ENVIO DE MENSAGENS
    # ==========================================
    def send_alert(self, item, analysis):
        """Envia um alerta de novo item encontrado."""
        if not self.bot or not self.chat_id:
            logger.warning("Bot nao configurado. Alerta nao enviado.")
            return

        emoji_rec = {
            "OTIMA OPORTUNIDADE": "\U0001f525",
            "BOA OPORTUNIDADE": "\U0001f44d",
            "REGULAR": "\u26a0\ufe0f",
            "NAO RECOMENDADO": "\u274c"
        }.get(analysis.get('recommendation', 'REGULAR'), "\u26a0\ufe0f")

        msg = f"\U0001f6a8 *NOVO ITEM ENCONTRADO* \U0001f6a8\n\n"
        msg += f"\U0001f4e6 *Item:* {item['title']}\n"
        msg += f"\U0001f3e2 *Site:* {item['site']}\n"
        msg += f"\U0001f4b0 *Preco Atual:* {item['price']}\n\n"

        msg += f"\U0001f916 *ANALISE DA IA:*\n"
        msg += f"\U0001f3f7 *Tipo:* {analysis.get('item_type', 'N/A')}\n"
        msg += f"\U0001f4b5 *Valor de Mercado:* {analysis.get('estimated_value', 'N/A')}\n"
        msg += f"\U0001f4c8 *Margem Estimada:* {analysis.get('profit_margin', 'N/A')}\n"
        msg += f"{emoji_rec} *Recomendacao:* {analysis.get('recommendation', 'N/A')}\n"
        msg += f"\U0001f4dd *Motivo:* {analysis.get('reasoning', 'N/A')}\n\n"

        # Adiciona comparacao com historico se disponivel
        history_comparison = analysis.get('history_comparison', '')
        if history_comparison:
            msg += f"{history_comparison}\n"

        msg += f"\U0001f517 [Acessar Leilao]({item['link']})"

        markup = InlineKeyboardMarkup()
        btn_agendar = InlineKeyboardButton("\U0001f4c5 Agendar", callback_data=f"agendar_{item['site']}")
        markup.add(btn_agendar)

        try:
            self.bot.send_message(
                self.chat_id, msg,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                reply_markup=markup
            )
            logger.info(f"Alerta enviado para {item['title']}")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta: {e}")

    def send_reminder(self, item, time_left):
        """Envia um lembrete de leilao agendado (legado)."""
        if not self.bot or not self.chat_id:
            return
        msg = f"\u23f0 *LEMBRETE DE LEILAO* \u23f0\n\n"
        msg += f"O leilao comeca em *{time_left}*!\n\n"
        msg += f"\U0001f4e6 *Item:* {item['title']}\n"
        msg += f"\U0001f3e2 *Site:* {item.get('site', 'N/A')}\n"
        min_bid = item.get('min_bid', 0) or 0
        msg += f"\U0001f4b0 *Lance Minimo:* ${min_bid:,.2f}\n\n"
        msg += f"\U0001f517 [Acessar Leilao]({item.get('link', '#')})"
        try:
            self.bot.send_message(self.chat_id, msg, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Erro ao enviar lembrete: {e}")

    def send_monthly_report(self, stats):
        """Envia o relatorio mensal."""
        if not self.bot or not self.chat_id:
            return
        lucro = stats.get('lucro_acumulado', 0)
        emoji = "\U0001f7e2" if lucro >= 0 else "\U0001f534"
        msg = f"\U0001f4ca *RELATORIO MENSAL DE LEILOES*\n\n"
        msg += f"\U0001f4c5 *Periodo:* {stats.get('periodo', 'Ultimo mes')}\n\n"
        msg += f"\U0001f4b8 *Total Investido:* ${stats.get('total_investido', 0):,.2f}\n"
        msg += f"\U0001f4c8 *Total em Vendas:* ${stats.get('total_vendas', 0):,.2f}\n"
        msg += f"{emoji} *Lucro/Prejuizo:* ${lucro:,.2f}\n\n"
        msg += f"\U0001f4e6 *Itens em Estoque:* {stats.get('em_estoque', 0)}\n"
        msg += f"\U0001f69a *Itens em Transito:* {stats.get('em_transito', 0)}\n"
        try:
            self.bot.send_message(self.chat_id, msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Erro ao enviar relatorio mensal: {e}")

    def start_polling(self):
        """Inicia o polling do bot em uma thread separada."""
        if self.bot:
            import threading
            thread = threading.Thread(target=self.bot.infinity_polling, daemon=True)
            thread.start()
            logger.info("Bot do Telegram iniciado.")
