"""
Utilitários para filtrar leilões ativos vs finalizados.
Usado por todos os scrapers para garantir consistência.
"""

import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('AuctionUtils')

# Palavras-chave que indicam leilão FINALIZADO
CLOSED_KEYWORDS = [
    'closed', 'ended', 'sold', 'completed', 'expired',
    'finalizado', 'encerrado', 'vendido', 'expirado',
    'archived', 'withdrawn', 'cancelled', 'canceled',
    'no longer available', 'not available', 'unavailable',
    'lote retirado', 'lote cancelado', 'fora de estoque',
]

# Palavras-chave que indicam leilão ATIVO
ACTIVE_KEYWORDS = [
    'active', 'open', 'bidding', 'live', 'ongoing',
    'ativo', 'aberto', 'em andamento', 'em leilão',
    'accepting bids', 'bid now', 'place bid',
    'aceita lances', 'faça seu lance',
]


def is_auction_closed(text):
    """Verifica se o texto contém indicadores de leilão finalizado."""
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Verifica palavras-chave de leilão fechado
    for keyword in CLOSED_KEYWORDS:
        if keyword in text_lower:
            return True
    
    return False


def is_auction_active(text):
    """Verifica se o texto contém indicadores de leilão ativo."""
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Verifica palavras-chave de leilão ativo
    for keyword in ACTIVE_KEYWORDS:
        if keyword in text_lower:
            return True
    
    return False


def extract_closing_time(text):
    """
    Tenta extrair data/hora de encerramento do texto.
    Retorna datetime ou None se não conseguir extrair.
    
    Padrões suportados:
    - "Closes: 2025-04-15 14:30 UTC"
    - "Ends: Apr 15, 2025 2:30 PM"
    - "Closing: 15/04/2025 14:30"
    - "Closes in 2 hours"
    """
    if not text:
        return None
    
    text = text.strip()
    now = datetime.utcnow()
    
    # Padrão 1: "Closes in X hours/minutes/days"
    match = re.search(r'closes?\s+in\s+(\d+)\s+(hours?|minutes?|days?)', text, re.IGNORECASE)
    if match:
        try:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            
            if 'hour' in unit:
                return now + timedelta(hours=amount)
            elif 'minute' in unit:
                return now + timedelta(minutes=amount)
            elif 'day' in unit:
                return now + timedelta(days=amount)
        except (ValueError, TypeError):
            pass
    
    # Padrão 2: ISO format "2025-04-15 14:30"
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', text)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5))
            )
        except (ValueError, TypeError):
            pass
    
    # Padrão 3: "Apr 15, 2025 2:30 PM"
    match = re.search(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(AM|PM)',
        text,
        re.IGNORECASE
    )
    if match:
        try:
            months = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = months[match.group(1).lower()[:3]]
            day = int(match.group(2))
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            ampm = match.group(6).upper()
            
            # Converte para 24h se necessário
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            
            return datetime(year, month, day, hour, minute)
        except (ValueError, TypeError):
            pass
    
    # Padrão 4: "15/04/2025 14:30" ou "04/15/2025 14:30"
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})', text)
    if match:
        try:
            # Tenta MM/DD/YYYY primeiro (formato americano)
            month = int(match.group(1))
            day = int(match.group(2))
            year = int(match.group(3))
            
            # Se mês > 12, inverte para DD/MM/YYYY
            if month > 12:
                month, day = day, month
            
            return datetime(year, month, day, int(match.group(4)), int(match.group(5)))
        except (ValueError, TypeError):
            pass
    
    return None


def is_auction_still_open(closing_time):
    """
    Verifica se um leilão ainda está aberto comparando com a hora atual.
    
    Args:
        closing_time: datetime do encerramento do leilão
    
    Returns:
        True se ainda está aberto, False se já encerrou
    """
    if not closing_time:
        return True  # Se não conseguir extrair data, assume que está aberto
    
    now = datetime.utcnow()
    
    # Adiciona 5 minutos de margem para evitar leilões que estão encerrando agora
    margin = timedelta(minutes=5)
    
    return now < (closing_time - margin)


def should_include_item(element_text, item_title=""):
    """
    Decisão final: incluir ou descartar um item?
    
    Retorna True se o item deve ser incluído (leilão ativo).
    Retorna False se o item deve ser descartado (leilão finalizado).
    """
    combined_text = f"{element_text} {item_title}".lower()
    
    # Se tem indicador explícito de fechado, descarta
    if is_auction_closed(combined_text):
        return False
    
    # Se tem indicador explícito de ativo, inclui
    if is_auction_active(combined_text):
        return True
    
    # Tenta extrair data de encerramento
    closing_time = extract_closing_time(element_text)
    if closing_time:
        return is_auction_still_open(closing_time)
    
    # Se não conseguir determinar, inclui por padrão
    # (melhor incluir um finalizado do que perder um ativo)
    return True
