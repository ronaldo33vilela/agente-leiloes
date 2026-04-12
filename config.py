import os

# ==========================================
# CONFIGURAÇÕES DO TELEGRAM
# ==========================================
# Substitua pelo Token do seu bot gerado no BotFather
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")

# Substitua pelo seu Chat ID (pode ser obtido enviando mensagem para @userinfobot)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "SEU_CHAT_ID_AQUI")

# ==========================================
# CONFIGURAÇÕES DE BUSCA
# ==========================================
# Palavras-chave para buscar nos sites de leilão
KEYWORDS = [
    "golf cart",
    "audio visual",
    "stage lighting",
    "sound equipment",
    "pa system",
    "speakers",
    "mixer",
    "amplifier",
    "projector",
    "led light"
]

# ==========================================
# CONFIGURAÇÕES DO SISTEMA
# ==========================================
# Intervalo de verificação em segundos (3600 = 1 hora)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))

# Caminho do banco de dados SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "auctions.db")

# Chave da API da OpenAI (já disponível no ambiente)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Headers para simular um navegador real e evitar bloqueios
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}
