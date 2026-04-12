import sqlite3
import os
from datetime import datetime
import sys

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def get_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    # Garante que o diretório do banco existe
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    return sqlite3.connect(config.DB_PATH)

def init_db():
    """Inicializa as tabelas do banco de dados se não existirem."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela de itens já notificados (para evitar duplicatas)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notified_items (
        id TEXT PRIMARY KEY,
        site TEXT,
        title TEXT,
        link TEXT,
        price TEXT,
        date_notified TIMESTAMP
    )
    ''')
    
    # Tabela da Agenda de Leilões
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
    
    # Tabela de Pós-Arrematação (Itens Ganhos)
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
    
    # Tabela de Estoque
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
    
    conn.commit()
    conn.close()

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

def mark_item_notified(item_id, site, title, link, price):
    """Marca um item como notificado."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO notified_items (id, site, title, link, price, date_notified)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (item_id, site, title, link, price, datetime.now()))
    conn.commit()
    conn.close()

# ==========================================
# FUNÇÕES DA AGENDA
# ==========================================
def add_to_agenda(title, site, link, auction_date, min_bid):
    """Adiciona um leilão à agenda."""
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
    """Retorna todos os itens da agenda que ainda não aconteceram."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM agenda 
    WHERE auction_date > ? 
    ORDER BY auction_date ASC
    ''', (datetime.now(),))
    items = cursor.fetchall()
    conn.close()
    return items

def remove_from_agenda(item_id):
    """Remove um item da agenda."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM agenda WHERE id = ?', (item_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_reminders_sent(item_id, reminder_type):
    """Atualiza quais lembretes já foram enviados para um item da agenda."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT reminders_sent FROM agenda WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    if row:
        current = row[0]
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
    items = cursor.fetchall()
    conn.close()
    return items

def move_to_inventory(won_item_id, description, suggested_price, condition):
    """Move um item ganho para o estoque."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Pega os dados do item ganho
    cursor.execute('SELECT * FROM won_items WHERE id = ?', (won_item_id,))
    won_item = cursor.fetchone()
    
    if not won_item:
        conn.close()
        return False
        
    # Atualiza status do item ganho
    cursor.execute("UPDATE won_items SET status = 'Entregue/Em Estoque' WHERE id = ?", (won_item_id,))
    
    # Insere no estoque
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
    items = cursor.fetchall()
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

def get_dashboard_stats():
    """Retorna estatísticas para o dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Leilões agendados
    cursor.execute("SELECT COUNT(*) FROM agenda WHERE auction_date > ?", (datetime.now(),))
    stats['agendados'] = cursor.fetchone()[0]
    
    # Itens em trânsito
    cursor.execute("SELECT COUNT(*) FROM won_items WHERE status = 'Em Trânsito'")
    stats['em_transito'] = cursor.fetchone()[0]
    
    # Itens em estoque
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE status = 'Disponível'")
    stats['em_estoque'] = cursor.fetchone()[0]
    
    # Total investido (itens em estoque + em trânsito)
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
    
    # Lucro acumulado (Vendas - Custo dos itens vendidos)
    cursor.execute("SELECT SUM(sale_price - price_paid) FROM inventory WHERE status = 'Vendido'")
    lucro = cursor.fetchone()[0]
    stats['lucro_acumulado'] = lucro if lucro else 0.0
    
    conn.close()
    return stats
