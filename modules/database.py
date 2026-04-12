import sqlite3
import os
from datetime import datetime
import sys
import logging

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger('Database')


def get_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """Inicializa todas as tabelas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    # --- Tabela de itens já notificados (evitar duplicatas) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notified_items (
        id TEXT PRIMARY KEY,
        site TEXT,
        title TEXT,
        link TEXT,
        price TEXT,
        keyword TEXT,
        category TEXT,
        date_notified TIMESTAMP
    )
    ''')

    # --- Tabela da Agenda / Watchlist de Leilões ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS auction_watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        site TEXT,
        category TEXT,
        current_price REAL DEFAULT 0,
        max_price_ceiling REAL DEFAULT 0,
        closing_date TIMESTAMP,
        status TEXT DEFAULT 'watching',
        reminders_sent TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # --- Tabela de Histórico de Preços Finais ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT,
        final_price REAL,
        closing_date TIMESTAMP,
        site TEXT,
        url TEXT,
        participated INTEGER DEFAULT 0,
        won INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # --- Tabela de Atualizações de Preço (rastrear evolução) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watchlist_id INTEGER NOT NULL,
        price REAL NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (watchlist_id) REFERENCES auction_watchlist (id)
    )
    ''')

    # --- Tabela de Pós-Arrematação (Itens Ganhos) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS won_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        site TEXT,
        link TEXT,
        price_paid REAL,
        win_date TIMESTAMP,
        location TEXT,
        status TEXT DEFAULT 'Aguardando Frete',
        carrier TEXT,
        tracking_number TEXT,
        tracking_status TEXT
    )
    ''')

    # --- Tabela de Estoque ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        won_item_id INTEGER,
        title TEXT,
        description TEXT,
        price_paid REAL,
        suggested_price REAL,
        condition TEXT,
        entry_date TIMESTAMP,
        status TEXT DEFAULT 'Disponível',
        sale_price REAL,
        sale_date TIMESTAMP,
        FOREIGN KEY (won_item_id) REFERENCES won_items (id)
    )
    ''')

    # --- Tabela legada de agenda (manter compatibilidade) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agenda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        site TEXT,
        link TEXT,
        auction_date TIMESTAMP,
        min_bid REAL,
        reminders_sent TEXT DEFAULT ''
    )
    ''')

    # Índices para performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watchlist_status ON auction_watchlist(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watchlist_closing ON auction_watchlist(closing_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_category ON price_history(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_title ON price_history(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_updates_watchlist ON price_updates(watchlist_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notified_keyword ON notified_items(keyword)')

    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado com sucesso.")


# ==========================================
# FUNÇÕES DE NOTIFICAÇÃO (EVITAR DUPLICATAS)
# ==========================================
def is_item_notified(item_id):
    """Verifica se um item já foi notificado."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM notified_items WHERE id = ?', (item_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_item_notified(item_id, site, title, link, price, keyword="", category=""):
    """Marca um item como notificado."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO notified_items (id, site, title, link, price, keyword, category, date_notified)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (item_id, site, title, link, price, keyword, category, datetime.now()))
    conn.commit()
    conn.close()


# ==========================================
# FUNÇÕES DA WATCHLIST / AGENDA DE LEILÕES
# ==========================================
def add_to_watchlist(title, url, site, category, current_price, max_price_ceiling, closing_date=None):
    """Adiciona um leilão à watchlist com preço teto."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO auction_watchlist (title, url, site, category, current_price, max_price_ceiling, closing_date, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'watching', ?)
    ''', (title, url, site, category, current_price, max_price_ceiling, closing_date, datetime.now()))
    item_id = cursor.lastrowid
    # Registra o preço inicial
    cursor.execute('''
    INSERT INTO price_updates (watchlist_id, price, timestamp)
    VALUES (?, ?, ?)
    ''', (item_id, current_price, datetime.now()))
    conn.commit()
    conn.close()
    return item_id


def get_watchlist_items(status='watching'):
    """Retorna itens da watchlist com o status especificado."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if status == 'all':
        cursor.execute('SELECT * FROM auction_watchlist ORDER BY closing_date ASC')
    else:
        cursor.execute('SELECT * FROM auction_watchlist WHERE status = ? ORDER BY closing_date ASC', (status,))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def get_watchlist_item(item_id):
    """Retorna um item específico da watchlist."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM auction_watchlist WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_watchlist_price(item_id, new_price):
    """Atualiza o preço atual de um item na watchlist e registra no histórico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE auction_watchlist SET current_price = ? WHERE id = ?', (new_price, item_id))
    cursor.execute('''
    INSERT INTO price_updates (watchlist_id, price, timestamp)
    VALUES (?, ?, ?)
    ''', (item_id, new_price, datetime.now()))
    conn.commit()
    conn.close()


def update_watchlist_ceiling(item_id, new_ceiling):
    """Atualiza o preço teto de um item na watchlist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE auction_watchlist SET max_price_ceiling = ? WHERE id = ?', (new_ceiling, item_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def update_watchlist_status(item_id, new_status):
    """Atualiza o status de um item na watchlist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE auction_watchlist SET status = ? WHERE id = ?', (new_status, item_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def update_watchlist_reminders(item_id, reminder_type):
    """Atualiza quais lembretes já foram enviados para um item da watchlist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT reminders_sent FROM auction_watchlist WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    if row:
        current = row[0] or ""
        new_reminders = f"{current},{reminder_type}" if current else reminder_type
        cursor.execute('UPDATE auction_watchlist SET reminders_sent = ? WHERE id = ?', (new_reminders, item_id))
    conn.commit()
    conn.close()


def remove_from_watchlist(item_id):
    """Remove um item da watchlist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM auction_watchlist WHERE id = ?', (item_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def archive_watchlist_item(item_id):
    """Move um item da watchlist para o arquivo."""
    return update_watchlist_status(item_id, 'archived')


def get_price_updates(watchlist_id, limit=50):
    """Retorna o histórico de atualizações de preço de um item."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM price_updates WHERE watchlist_id = ? ORDER BY timestamp DESC LIMIT ?
    ''', (watchlist_id, limit))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


# ==========================================
# FUNÇÕES DO HISTÓRICO DE PREÇOS
# ==========================================
def add_price_history(title, category, final_price, closing_date, site, url, participated=False, won=False):
    """Registra o preço final de um leilão no histórico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO price_history (title, category, final_price, closing_date, site, url, participated, won, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, category, final_price, closing_date, site, url,
          1 if participated else 0, 1 if won else 0, datetime.now()))
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return item_id


def get_price_history(category=None, limit=100):
    """Retorna o histórico de preços, opcionalmente filtrado por categoria."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if category:
        cursor.execute('''
        SELECT * FROM price_history WHERE category = ? ORDER BY closing_date DESC LIMIT ?
        ''', (category, limit))
    else:
        cursor.execute('SELECT * FROM price_history ORDER BY closing_date DESC LIMIT ?', (limit,))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def search_price_history(search_term, limit=20):
    """Busca no histórico de preços por termo (título)."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM price_history WHERE title LIKE ? ORDER BY closing_date DESC LIMIT ?
    ''', (f'%{search_term}%', limit))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def get_average_price(search_term):
    """Retorna o preço médio de arrematação de um produto."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT AVG(final_price) as avg_price, MIN(final_price) as min_price,
           MAX(final_price) as max_price, COUNT(*) as total
    FROM price_history WHERE title LIKE ? AND final_price > 0
    ''', (f'%{search_term}%',))
    row = cursor.fetchone()
    conn.close()
    if row and row[3] > 0:
        return {
            "avg_price": round(row[0], 2),
            "min_price": round(row[1], 2),
            "max_price": round(row[2], 2),
            "total_records": row[3]
        }
    return None


def get_last_similar_auction(search_term):
    """Retorna o último leilão similar encontrado no histórico."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM price_history WHERE title LIKE ? AND final_price > 0
    ORDER BY closing_date DESC LIMIT 1
    ''', (f'%{search_term}%',))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_price_history_by_category_stats():
    """Retorna estatísticas de preço agrupadas por categoria."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT category, COUNT(*) as total, AVG(final_price) as avg_price,
           MIN(final_price) as min_price, MAX(final_price) as max_price
    FROM price_history WHERE final_price > 0
    GROUP BY category ORDER BY total DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    stats = []
    for row in rows:
        stats.append({
            "category": row[0] or "Sem categoria",
            "total": row[1],
            "avg_price": round(row[2], 2) if row[2] else 0,
            "min_price": round(row[3], 2) if row[3] else 0,
            "max_price": round(row[4], 2) if row[4] else 0,
        })
    return stats


# ==========================================
# FUNÇÕES DA AGENDA LEGADA (compatibilidade)
# ==========================================
def add_to_agenda(title, site, link, auction_date, min_bid):
    """Adiciona um leilão à agenda (legado)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO agenda (title, site, link, auction_date, min_bid)
    VALUES (?, ?, ?, ?, ?)
    ''', (title, site, link, auction_date, min_bid))
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return item_id


def get_agenda_items():
    """Retorna todos os itens da agenda que ainda não aconteceram (legado)."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM agenda
    WHERE auction_date > ?
    ORDER BY auction_date ASC
    ''', (datetime.now(),))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def remove_from_agenda(item_id):
    """Remove um item da agenda (legado)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM agenda WHERE id = ?', (item_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_reminders_sent(item_id, reminder_type):
    """Atualiza quais lembretes já foram enviados (legado)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT reminders_sent FROM agenda WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    if row:
        current = row[0] or ""
        new_reminders = f"{current},{reminder_type}" if current else reminder_type
        cursor.execute('UPDATE agenda SET reminders_sent = ? WHERE id = ?', (new_reminders, item_id))
    conn.commit()
    conn.close()


# ==========================================
# FUNÇÕES DE PÓS-ARREMATAÇÃO E ESTOQUE
# ==========================================
def add_won_item(title, site, price_paid, location):
    """Registra um lote ganho."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO won_items (title, site, price_paid, win_date, location)
    VALUES (?, ?, ?, ?, ?)
    ''', (title, site, price_paid, datetime.now(), location))
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return item_id


def update_shipping(item_id, carrier, tracking_number):
    """Atualiza informações de frete de um lote ganho."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE won_items
    SET carrier = ?, tracking_number = ?, status = 'Em Trânsito'
    WHERE id = ?
    ''', (carrier, tracking_number, item_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_transit_items():
    """Retorna itens em trânsito."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM won_items WHERE status = 'Em Trânsito'")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def move_to_inventory(won_item_id, description, suggested_price, condition):
    """Move um item ganho para o estoque."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM won_items WHERE id = ?', (won_item_id,))
    won_item = cursor.fetchone()
    if not won_item:
        conn.close()
        return False
    cursor.execute("UPDATE won_items SET status = 'Entregue/Em Estoque' WHERE id = ?", (won_item_id,))
    cursor.execute('''
    INSERT INTO inventory (won_item_id, title, description, price_paid, suggested_price, condition, entry_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (won_item_id, won_item['title'], description, won_item['price_paid'], suggested_price, condition, datetime.now()))
    conn.commit()
    conn.close()
    return True


def get_inventory():
    """Retorna itens disponíveis no estoque."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE status = 'Disponível'")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def sell_item(inventory_id, sale_price):
    """Marca um item do estoque como vendido."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE inventory
    SET status = 'Vendido', sale_price = ?, sale_date = ?
    WHERE id = ?
    ''', (sale_price, datetime.now(), inventory_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


# ==========================================
# FUNÇÕES DE DASHBOARD / ESTATÍSTICAS
# ==========================================
def get_dashboard_stats():
    """Retorna estatísticas completas para o dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    # Leilões na watchlist
    cursor.execute("SELECT COUNT(*) FROM auction_watchlist WHERE status = 'watching'")
    stats['watching'] = cursor.fetchone()[0]

    # Leilões arquivados
    cursor.execute("SELECT COUNT(*) FROM auction_watchlist WHERE status = 'archived'")
    stats['archived'] = cursor.fetchone()[0]

    # Leilões agendados (legado)
    try:
        cursor.execute("SELECT COUNT(*) FROM agenda WHERE auction_date > ?", (datetime.now(),))
        stats['agendados'] = cursor.fetchone()[0]
    except Exception:
        stats['agendados'] = 0

    # Itens em trânsito
    cursor.execute("SELECT COUNT(*) FROM won_items WHERE status = 'Em Trânsito'")
    stats['em_transito'] = cursor.fetchone()[0]

    # Itens em estoque
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE status = 'Disponível'")
    stats['em_estoque'] = cursor.fetchone()[0]

    # Total investido
    cursor.execute('''
    SELECT SUM(price_paid) FROM won_items
    WHERE status IN ('Aguardando Frete', 'Em Trânsito', 'Entregue/Em Estoque')
    ''')
    investido = cursor.fetchone()[0]
    stats['total_investido'] = investido if investido else 0.0

    # Total em vendas
    cursor.execute("SELECT SUM(sale_price) FROM inventory WHERE status = 'Vendido'")
    vendas = cursor.fetchone()[0]
    stats['total_vendas'] = vendas if vendas else 0.0

    # Lucro acumulado
    cursor.execute("SELECT SUM(sale_price - price_paid) FROM inventory WHERE status = 'Vendido'")
    lucro = cursor.fetchone()[0]
    stats['lucro_acumulado'] = lucro if lucro else 0.0

    # Total no histórico de preços
    cursor.execute("SELECT COUNT(*) FROM price_history")
    stats['total_historico'] = cursor.fetchone()[0]

    conn.close()
    return stats


def get_archived_items(category=None):
    """Retorna itens arquivados, opcionalmente filtrados por categoria."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if category:
        cursor.execute('''
        SELECT * FROM auction_watchlist WHERE status = 'archived' AND category = ?
        ORDER BY created_at DESC
        ''', (category,))
    else:
        cursor.execute("SELECT * FROM auction_watchlist WHERE status = 'archived' ORDER BY created_at DESC")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items
