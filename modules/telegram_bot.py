import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import sys
import os
from datetime import datetime

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from modules import database

logger = logging.getLogger('TelegramBot')

class AuctionTelegramBot:
    """Módulo para gerenciar a comunicação com o Telegram."""
    
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        
        if not self.token or self.token == "SEU_TOKEN_AQUI":
            logger.warning("TELEGRAM_TOKEN não configurado. O bot não funcionará.")
            self.bot = None
        else:
            self.bot = telebot.TeleBot(self.token)
            self._setup_handlers()
            
    def _check_auth(self, message):
        """Verifica se o usuário está autorizado."""
        return str(message.chat.id) == str(self.chat_id)
            
    def _setup_handlers(self):
        """Configura os comandos do bot."""
        
        # ==========================================
        # COMANDO /start e /help
        # ==========================================
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            if not self._check_auth(message):
                self.bot.reply_to(message, "Acesso negado. Este bot é privado.")
                return
                
            help_text = (
                "🤖 *Agente de Leilões Americanos*\n\n"
                "*Comandos Disponíveis:*\n\n"
                "*Monitoramento:*\n"
                "/buscar [termo] - Busca manual nos sites\n\n"
                "*Agenda:*\n"
                "/agendar - Registra um leilão na agenda\n"
                "/agenda - Lista todos os leilões agendados\n"
                "/cancelar [ID] - Remove um leilão da agenda\n\n"
                "*Pós-Arrematação:*\n"
                "/ganhou - Registra um lote arrematado\n"
                "/frete [ID] - Registra frete/transportadora\n"
                "/rastrear - Consulta status de itens em trânsito\n"
                "/entregue [ID] - Marca item como entregue\n\n"
                "*Estoque e Vendas:*\n"
                "/estoque - Lista itens disponíveis para venda\n"
                "/vender [ID] [Valor] - Marca um item como vendido\n"
                "/dashboard - Resumo completo de investimentos e lucros\n"
            )
            self.bot.reply_to(message, help_text, parse_mode='Markdown')
            
        # ==========================================
        # COMANDO /agendar
        # ==========================================
        @self.bot.message_handler(commands=['agendar'])
        def agendar_leilao(message):
            if not self._check_auth(message): return
            
            msg = self.bot.reply_to(
                message, 
                "📅 Para agendar um leilão, responda com os dados no formato:\n"
                "`Data (DD/MM/AAAA HH:MM) | Lance Mínimo | Título | Site | Link`\n\n"
                "Exemplo:\n"
                "`15/04/2026 14:30 | 500.00 | Golf Cart EZGO | GovDeals | https://www.govdeals.com/en/asset/123/456`",
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(msg, self._process_agenda)
            
        # ==========================================
        # COMANDO /agenda
        # ==========================================
        @self.bot.message_handler(commands=['agenda'])
        def list_agenda(message):
            if not self._check_auth(message): return
            
            items = database.get_agenda_items()
            if not items:
                self.bot.reply_to(message, "📅 Sua agenda está vazia.")
                return
                
            response = "📅 *LEILÕES AGENDADOS*\n\n"
            for item in items:
                try:
                    date_str = datetime.strptime(
                        str(item['auction_date']), '%Y-%m-%d %H:%M:%S.%f'
                    ).strftime('%d/%m/%Y %H:%M')
                except:
                    try:
                        date_str = datetime.strptime(
                            str(item['auction_date']), '%Y-%m-%d %H:%M:%S'
                        ).strftime('%d/%m/%Y %H:%M')
                    except:
                        date_str = str(item['auction_date'])
                        
                response += f"🆔 *ID:* {item['id']}\n"
                response += f"📦 *Item:* {item['title']}\n"
                response += f"🏢 *Site:* {item['site']}\n"
                response += f"⏰ *Data:* {date_str}\n"
                response += f"💰 *Lance Mínimo:* ${item['min_bid']:.2f}\n"
                response += f"🔗 [Link do Leilão]({item['link']})\n"
                response += "------------------------\n"
                
            self.bot.reply_to(message, response, parse_mode='Markdown', disable_web_page_preview=True)
            
        # ==========================================
        # COMANDO /cancelar
        # ==========================================
        @self.bot.message_handler(commands=['cancelar'])
        def cancel_agenda(message):
            if not self._check_auth(message): return
            
            try:
                item_id = int(message.text.split()[1])
                if database.remove_from_agenda(item_id):
                    self.bot.reply_to(message, f"✅ Item {item_id} removido da agenda com sucesso.")
                else:
                    self.bot.reply_to(message, f"❌ Item {item_id} não encontrado na agenda.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "❌ Formato incorreto. Use: /cancelar [ID]")
                
        # ==========================================
        # COMANDO /ganhou
        # ==========================================
        @self.bot.message_handler(commands=['ganhou'])
        def register_win(message):
            if not self._check_auth(message): return
            
            msg = self.bot.reply_to(
                message, 
                "🎉 Parabéns pela arrematação!\n\n"
                "Responda esta mensagem com os dados no formato:\n"
                "`Nome do Item | Site | Valor Pago | Localização (Cidade, Estado)`\n\n"
                "Exemplo:\n"
                "`Golf Cart EZGO | GovDeals | 1500.00 | Miami, FL`",
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(msg, self._process_win)
            
        # ==========================================
        # COMANDO /frete
        # ==========================================
        @self.bot.message_handler(commands=['frete'])
        def register_freight(message):
            if not self._check_auth(message): return
            
            try:
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    raise ValueError("Parâmetros insuficientes")
                    
                # Formato: /frete ID | Transportadora | CodigoRastreio
                data_parts = [p.strip() for p in parts[1].split('|')]
                if len(data_parts) != 3:
                    raise ValueError("Formato incorreto")
                    
                item_id = int(data_parts[0])
                carrier = data_parts[1]
                tracking_number = data_parts[2]
                
                if database.update_shipping(item_id, carrier, tracking_number):
                    self.bot.reply_to(
                        message, 
                        f"✅ Frete registrado com sucesso!\n\n"
                        f"📦 *Item ID:* {item_id}\n"
                        f"🚚 *Transportadora:* {carrier}\n"
                        f"🔢 *Rastreio:* `{tracking_number}`\n\n"
                        f"Você receberá atualizações automáticas de rastreamento.",
                        parse_mode='Markdown'
                    )
                else:
                    self.bot.reply_to(message, f"❌ Item {item_id} não encontrado nos lotes ganhos.")
            except (ValueError, IndexError):
                self.bot.reply_to(
                    message, 
                    "❌ Formato incorreto. Use:\n"
                    "`/frete ID | Transportadora | CodigoRastreio`\n\n"
                    "Exemplo:\n"
                    "`/frete 1 | FedEx | 123456789012`",
                    parse_mode='Markdown'
                )
                
        # ==========================================
        # COMANDO /rastrear
        # ==========================================
        @self.bot.message_handler(commands=['rastrear'])
        def track_items(message):
            if not self._check_auth(message): return
            
            items = database.get_transit_items()
            if not items:
                self.bot.reply_to(message, "🚚 Não há itens em trânsito no momento.")
                return
                
            response = "🚚 *ITENS EM TRÂNSITO*\n\n"
            for item in items:
                response += f"🆔 *ID:* {item['id']}\n"
                response += f"📦 *Item:* {item['title']}\n"
                response += f"🏢 *Transportadora:* {item['carrier']}\n"
                response += f"🔢 *Rastreio:* `{item['tracking_number']}`\n"
                response += f"📍 *Status:* {item['tracking_status'] or 'Aguardando atualização'}\n"
                response += "------------------------\n"
                
            self.bot.reply_to(message, response, parse_mode='Markdown')
            
        # ==========================================
        # COMANDO /entregue
        # ==========================================
        @self.bot.message_handler(commands=['entregue'])
        def mark_delivered(message):
            if not self._check_auth(message): return
            
            try:
                item_id = int(message.text.split()[1])
                
                # Move para o estoque com preço sugerido de 1.5x o valor pago
                if database.move_to_inventory(item_id, "Item entregue via leilão", 0, "Usado - Ver descrição"):
                    self.bot.reply_to(
                        message, 
                        f"✅ Item {item_id} marcado como entregue e adicionado ao estoque!\n"
                        f"Use /estoque para ver seus itens disponíveis."
                    )
                else:
                    self.bot.reply_to(message, f"❌ Item {item_id} não encontrado nos lotes ganhos.")
            except (IndexError, ValueError):
                self.bot.reply_to(message, "❌ Formato incorreto. Use: /entregue [ID]")
                
        # ==========================================
        # COMANDO /estoque
        # ==========================================
        @self.bot.message_handler(commands=['estoque'])
        def list_inventory(message):
            if not self._check_auth(message): return
            
            items = database.get_inventory()
            if not items:
                self.bot.reply_to(message, "📦 Seu estoque está vazio.")
                return
                
            response = "📦 *ESTOQUE DISPONÍVEL*\n\n"
            for item in items:
                response += f"🆔 *ID:* {item['id']}\n"
                response += f"📦 *Item:* {item['title']}\n"
                response += f"💰 *Custo:* ${item['price_paid']:.2f}\n"
                response += f"🏷️ *Preço Sugerido:* ${item['suggested_price']:.2f}\n"
                response += f"⭐ *Condição:* {item['condition']}\n"
                response += "------------------------\n"
                
            self.bot.reply_to(message, response, parse_mode='Markdown')
            
        # ==========================================
        # COMANDO /vender
        # ==========================================
        @self.bot.message_handler(commands=['vender'])
        def sell_item(message):
            if not self._check_auth(message): return
            
            try:
                parts = message.text.split()
                item_id = int(parts[1])
                sale_price = float(parts[2])
                
                if database.sell_item(item_id, sale_price):
                    self.bot.reply_to(message, f"✅ Item {item_id} marcado como vendido por ${sale_price:.2f}!")
                else:
                    self.bot.reply_to(message, f"❌ Item {item_id} não encontrado no estoque.")
            except (IndexError, ValueError):
                self.bot.reply_to(
                    message, 
                    "❌ Formato incorreto. Use: /vender [ID] [Valor]\n"
                    "Exemplo: /vender 5 2500.00"
                )
                
        # ==========================================
        # COMANDO /dashboard
        # ==========================================
        @self.bot.message_handler(commands=['dashboard'])
        def show_dashboard(message):
            if not self._check_auth(message): return
            
            stats = database.get_dashboard_stats()
            
            response = "📊 *DASHBOARD DE LEILÕES*\n\n"
            response += f"📅 *Leilões Agendados:* {stats['agendados']}\n"
            response += f"🚚 *Itens em Trânsito:* {stats['em_transito']}\n"
            response += f"📦 *Itens em Estoque:* {stats['em_estoque']}\n\n"
            
            response += f"💸 *Total Investido:* ${stats['total_investido']:.2f}\n"
            response += f"📈 *Total em Vendas:* ${stats['total_vendas']:.2f}\n"
            
            lucro = stats['lucro_acumulado']
            emoji = "🟢" if lucro >= 0 else "🔴"
            response += f"{emoji} *Lucro Acumulado:* ${lucro:.2f}\n"
            
            self.bot.reply_to(message, response, parse_mode='Markdown')
            
        # ==========================================
        # CALLBACK: Botão Agendar (inline)
        # ==========================================
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('agendar_'))
        def callback_agendar(call):
            if str(call.message.chat.id) != str(self.chat_id): return
            
            msg = self.bot.send_message(
                call.message.chat.id, 
                "📅 Para agendar, responda com:\n"
                "`Data (DD/MM/AAAA HH:MM) | Lance Mínimo | Título | Site | Link`\n\n"
                "Exemplo:\n"
                "`15/04/2026 14:30 | 500.00 | Golf Cart | GovDeals | https://...`",
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(msg, self._process_agenda)
            self.bot.answer_callback_query(call.id)
            
    # ==========================================
    # PROCESSADORES DE RESPOSTAS
    # ==========================================
    def _process_win(self, message):
        """Processa a resposta do comando /ganhou."""
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) != 4:
                raise ValueError("Número incorreto de parâmetros (esperado: 4)")
                
            title, site, price_str, location = parts
            price = float(price_str.replace('$', '').replace(',', ''))
            
            item_id = database.add_won_item(title, site, price, location)
            
            response = (
                f"✅ Lote registrado com sucesso! (ID: {item_id})\n\n"
                f"Para registrar o frete, use o comando:\n"
                f"`/frete {item_id} | Transportadora | CodigoRastreio`"
            )
            
            self.bot.reply_to(message, response, parse_mode='Markdown')
            
        except Exception as e:
            self.bot.reply_to(
                message, 
                f"❌ Erro ao processar: {e}\n"
                f"Por favor, tente novamente usando o formato correto."
            )
            
    def _process_agenda(self, message):
        """Processa a resposta para agendar um leilão."""
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) != 5:
                raise ValueError("Número incorreto de parâmetros (esperado: 5)")
                
            date_str, min_bid_str, title, site, link = parts
            
            auction_date = datetime.strptime(date_str, '%d/%m/%Y %H:%M')
            min_bid = float(min_bid_str.replace('$', '').replace(',', ''))
            
            item_id = database.add_to_agenda(title, site, link, auction_date, min_bid)
            
            self.bot.reply_to(
                message, 
                f"✅ Leilão agendado com sucesso! (ID: {item_id})\n"
                f"Você receberá lembretes 24h, 1h e 15m antes."
            )
            
        except Exception as e:
            self.bot.reply_to(
                message, 
                f"❌ Erro ao processar: {e}\n"
                f"Por favor, tente novamente usando o formato correto."
            )
            
    # ==========================================
    # MÉTODOS DE ENVIO DE MENSAGENS
    # ==========================================
    def send_alert(self, item, analysis):
        """Envia um alerta de novo item encontrado."""
        if not self.bot or not self.chat_id:
            logger.warning("Bot não configurado. Alerta não enviado.")
            return
            
        emoji_rec = {
            "ÓTIMA OPORTUNIDADE": "🔥",
            "BOA OPORTUNIDADE": "👍",
            "REGULAR": "⚠️",
            "NÃO RECOMENDADO": "❌"
        }.get(analysis.get('recommendation', 'REGULAR'), "⚠️")
        
        msg = f"🚨 *NOVO ITEM ENCONTRADO* 🚨\n\n"
        msg += f"📦 *Item:* {item['title']}\n"
        msg += f"🏢 *Site:* {item['site']}\n"
        msg += f"💰 *Preço Atual:* {item['price']}\n\n"
        
        msg += f"🤖 *ANÁLISE DA IA:*\n"
        msg += f"🏷️ *Tipo:* {analysis.get('item_type', 'N/A')}\n"
        msg += f"💵 *Valor de Mercado:* {analysis.get('estimated_value', 'N/A')}\n"
        msg += f"📈 *Margem Estimada:* {analysis.get('profit_margin', 'N/A')}\n"
        msg += f"{emoji_rec} *Recomendação:* {analysis.get('recommendation', 'N/A')}\n"
        msg += f"📝 *Motivo:* {analysis.get('reasoning', 'N/A')}\n\n"
        
        msg += f"🔗 [Acessar Leilão]({item['link']})"
        
        markup = InlineKeyboardMarkup()
        btn_agendar = InlineKeyboardButton("📅 Agendar Lembrete", callback_data=f"agendar_{item['site']}")
        markup.add(btn_agendar)
        
        try:
            self.bot.send_message(
                self.chat_id, 
                msg, 
                parse_mode='Markdown', 
                disable_web_page_preview=True,
                reply_markup=markup
            )
            logger.info(f"Alerta enviado para {item['title']}")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta: {e}")
            
    def send_reminder(self, item, time_left):
        """Envia um lembrete de leilão agendado."""
        if not self.bot or not self.chat_id: return
        
        msg = f"⏰ *LEMBRETE DE LEILÃO* ⏰\n\n"
        msg += f"O leilão do item abaixo começa em *{time_left}*!\n\n"
        msg += f"📦 *Item:* {item['title']}\n"
        msg += f"🏢 *Site:* {item['site']}\n"
        msg += f"💰 *Lance Mínimo:* ${item['min_bid']:.2f}\n\n"
        msg += f"🔗 [Acessar Leilão]({item['link']})"
        
        try:
            self.bot.send_message(self.chat_id, msg, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Erro ao enviar lembrete: {e}")
            
    def send_monthly_report(self, stats):
        """Envia o relatório mensal de lucro/prejuízo."""
        if not self.bot or not self.chat_id: return
        
        lucro = stats['lucro_acumulado']
        emoji = "🟢" if lucro >= 0 else "🔴"
        
        msg = f"📊 *RELATÓRIO MENSAL DE LEILÕES*\n\n"
        msg += f"📅 *Período:* {stats.get('periodo', 'Último mês')}\n\n"
        msg += f"💸 *Total Investido:* ${stats['total_investido']:.2f}\n"
        msg += f"📈 *Total em Vendas:* ${stats['total_vendas']:.2f}\n"
        msg += f"{emoji} *Lucro/Prejuízo:* ${lucro:.2f}\n\n"
        msg += f"📦 *Itens em Estoque:* {stats['em_estoque']}\n"
        msg += f"🚚 *Itens em Trânsito:* {stats['em_transito']}\n"
        
        try:
            self.bot.send_message(self.chat_id, msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Erro ao enviar relatório mensal: {e}")
            
    def start_polling(self):
        """Inicia o polling do bot em uma thread separada."""
        if self.bot:
            import threading
            thread = threading.Thread(target=self.bot.infinity_polling)
            thread.daemon = True
            thread.start()
            logger.info("Bot do Telegram iniciado.")
