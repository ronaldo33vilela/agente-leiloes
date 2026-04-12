import time
import threading
import logging
import sys
import os
from datetime import datetime, timedelta

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import database

logger = logging.getLogger('Agenda')

class AgendaManager:
    """Módulo para gerenciar a agenda de leilões e enviar lembretes."""
    
    def __init__(self, telegram_bot):
        self.bot = telegram_bot
        self.running = False
        self.thread = None
        
    def start(self):
        """Inicia o loop de verificação da agenda em uma thread separada."""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._check_loop)
        self.thread.daemon = True
        self.thread.start()
        logger.info("Gerenciador de agenda iniciado.")
        
    def stop(self):
        """Para o loop de verificação."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def _check_loop(self):
        """Loop principal que verifica os leilões agendados a cada minuto."""
        while self.running:
            try:
                self._check_reminders()
            except Exception as e:
                logger.error(f"Erro ao verificar agenda: {e}")
                
            # Verifica a cada 60 segundos
            time.sleep(60)
            
    def _check_reminders(self):
        """Verifica se há lembretes a serem enviados."""
        items = database.get_agenda_items()
        now = datetime.now()
        
        for item in items:
            try:
                # Converte a string de data do banco para objeto datetime
                auction_date = datetime.strptime(item['auction_date'], '%Y-%m-%d %H:%M:%S.%f')
                time_diff = auction_date - now
                
                # Pega os lembretes já enviados
                sent_reminders = item['reminders_sent'].split(',') if item['reminders_sent'] else []
                
                # Lembrete de 24 horas
                if timedelta(hours=23, minutes=55) <= time_diff <= timedelta(hours=24, minutes=5):
                    if '24h' not in sent_reminders:
                        self.bot.send_reminder(item, "24 horas")
                        database.update_reminders_sent(item['id'], '24h')
                        
                # Lembrete de 1 hora
                elif timedelta(minutes=55) <= time_diff <= timedelta(hours=1, minutes=5):
                    if '1h' not in sent_reminders:
                        self.bot.send_reminder(item, "1 hora")
                        database.update_reminders_sent(item['id'], '1h')
                        
                # Lembrete de 15 minutos
                elif timedelta(minutes=10) <= time_diff <= timedelta(minutes=15):
                    if '15m' not in sent_reminders:
                        self.bot.send_reminder(item, "15 minutos")
                        database.update_reminders_sent(item['id'], '15m')
                        
            except Exception as e:
                logger.error(f"Erro ao processar lembrete para o item {item['id']}: {e}")
