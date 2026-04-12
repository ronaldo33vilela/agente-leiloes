import os

# ==========================================
# CREDENCIAIS (lidas de variáveis de ambiente)
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "SEU_CHAT_ID_AQUI")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ==========================================
# INTERVALO DE MONITORAMENTO
# ==========================================
# Intervalo de verificação em segundos (3600 = 1 hora)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))

# ==========================================
# BANCO DE DADOS
# ==========================================
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "auctions.db")

# ==========================================
# HEADERS HTTP (simula navegador real)
# ==========================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
}

# ==========================================
# TERMOS DE BUSCA — ORGANIZADOS POR CATEGORIA
# ==========================================
# Cada categoria contém uma lista de termos que serão rotacionados
# automaticamente a cada ciclo de monitoramento.

SEARCH_TERMS = {

    # ------------------------------------------------------------------
    # 1. Allen & Heath — mesas principais
    # ------------------------------------------------------------------
    "allen_heath_mixers": [
        # Série SQ
        "Allen Heath SQ5",
        "Allen Heath SQ6",
        "Allen Heath SQ7",
        "Allen and Heath SQ5",
        "Allen and Heath SQ6",
        "Allen and Heath SQ7",
        # Série Qu
        "Allen Heath Qu16",
        "Allen Heath Qu24",
        "Allen Heath Qu32",
        "Allen and Heath Qu16",
        "Allen and Heath Qu24",
        "Allen and Heath Qu32",
        # Série GLD / iLive / Avantis / dLive
        "Allen Heath GLD80",
        "Allen Heath GLD112",
        "Allen Heath iLive",
        "Allen Heath Avantis",
        "Allen Heath dLive",
        "Allen Heath C1500",
        "Allen Heath C3500",
        "Allen Heath CDM32",
        "Allen Heath CDM48",
        "Allen Heath DM32",
        "Allen Heath DM48",
        # Modelos adicionais
        "Allen Heath M1",
        "Allen Heath M500",
        "Allen and Heath M1",
        "Allen and Heath M500",
    ],

    # ------------------------------------------------------------------
    # 2. Allen & Heath — acessórios e expansão
    # ------------------------------------------------------------------
    "allen_heath_accessories": [
        # Stagebox / expansões
        "Allen Heath stagebox",
        "Allen Heath AR2412",
        "Allen Heath AR84",
        "Allen Heath AB168",
        "Allen Heath DX168",
        "Allen Heath DX32",
        "Allen Heath GX4816",
        "Allen Heath MixRack",
        "Allen Heath dSnake",
        "Allen Heath expander",
        # Placas / rede / áudio
        "Allen Heath Dante card",
        "Allen Heath network card",
        "Allen Heath expansion card",
        "Allen Heath gigaACE",
        "Allen Heath Waves card",
        "Allen Heath MADI card",
        "Allen Heath SLink",
        "Allen Heath audio interface card",
        # Cabos / snakes / extensões
        "Allen Heath snake cable",
        "Allen Heath cat5 snake",
        "Allen Heath ethercon cable",
        "Allen Heath dSnake cable",
        "digital snake cable",
        "audio snake reel",
        "stage cable reel",
        # Cases / flight cases / racks
        "Allen Heath case",
        "Allen Heath flight case",
        "Allen Heath mixer case",
        "Allen Heath road case",
        "SQ5 flight case",
        "Qu32 flight case",
        "audio rack case",
        "mixer rack case",
        # Fontes / peças / itens úteis
        "Allen Heath power supply",
        "Allen Heath PSU",
        "Allen Heath replacement power supply",
        "Allen Heath touchscreen",
        "Allen Heath spare parts",
        "Allen Heath fader board",
    ],

    # ------------------------------------------------------------------
    # 3. Allen & Heath — buscas inteligentes
    # ------------------------------------------------------------------
    "allen_heath_smart": [
        # Lote completo
        "Allen Heath audio system lot",
        "Allen Heath mixer with stagebox",
        "Allen Heath church audio",
        "Allen Heath digital mixer lot",
        "Allen Heath rack system",
        # Anúncio mal escrito
        "Allen and Heath mixer",
        "AllenHeath mixer",
        "Alen Heath mixer",
        # Oportunidade barata
        "Allen Heath untested",
        "Allen Heath as-is",
        "Allen Heath for parts",
        "Allen Heath surplus",
    ],

    # ------------------------------------------------------------------
    # 4. Shure Axient — linha principal
    # ------------------------------------------------------------------
    "shure_axient": [
        "Shure Axient",
        "Shure Axient Digital",
        "Shure AD4D",
        "Shure AD4Q",
        "Shure AD1",
        "Shure AD2",
        "Shure AXT400",
        "Shure AXT600",
        "Shure AXT900",
        "Shure AXT910",
        "Shure AXT920",
        "Shure AXT630",
        "Shure AXT650",
        "Shure ADX1",
        "Shure ADX2",
        "Shure ADX5D",
    ],

    # ------------------------------------------------------------------
    # 5. Shure Axient — acessórios
    # ------------------------------------------------------------------
    "shure_axient_accessories": [
        "Shure Axient antenna",
        "Shure Axient antenna distribution",
        "Shure Axient charger",
        "Shure Axient battery charger",
        "Shure SBRC",
        "Shure SB900",
        "Shure SB910",
        "Shure UA844",
        "Shure UA874",
        "Shure UA845",
        "Shure wireless mic rack",
        "Shure receiver rack",
    ],

    # ------------------------------------------------------------------
    # 6. Shure Axient — buscas prontas
    # ------------------------------------------------------------------
    "shure_axient_smart": [
        "Shure Axient lot",
        "Shure Axient Digital lot",
        "Shure AD4D lot",
        "Shure Axient rack",
        "Shure Axient church audio",
        "Shure Axient untested",
        "Shure Axient as-is",
    ],

    # ------------------------------------------------------------------
    # 7. Mesas de luz — marcas e linhas
    # ------------------------------------------------------------------
    "lighting_consoles": [
        "MA Lighting grandMA2",
        "MA Lighting grandMA3",
        "grandMA2 light",
        "grandMA2 ultra light",
        "grandMA2 command wing",
        "grandMA3 compact",
        "grandMA3 command wing",
        "Avolites Tiger Touch",
        "Avolites Quartz",
        "Avolites Arena",
        "Chamsys MQ70",
        "Chamsys MQ80",
        "Chamsys MQ250",
        "ETC Ion",
        "ETC Gio",
        "Hog 4",
        "Road Hog",
        "Wholehog",
    ],

    # ------------------------------------------------------------------
    # 8. Mesas de luz — termos genéricos e acessórios
    # ------------------------------------------------------------------
    "lighting_accessories": [
        # Termos genéricos
        "lighting console",
        "stage lighting console",
        "DMX console",
        "lighting desk",
        "theater lighting console",
        # Acessórios de luz
        "DMX node",
        "artnet node",
        "lighting wing",
        "playback wing",
        "timecode lighting",
        "lighting flight case",
        "console road case",
    ],

    # ------------------------------------------------------------------
    # 9. Mesas de luz — buscas prontas
    # ------------------------------------------------------------------
    "lighting_smart": [
        "lighting console lot",
        "stage lighting lot",
        "grandMA2 with case",
        "Avolites console lot",
        "Chamsys lighting console",
        "lighting console untested",
    ],

    # ------------------------------------------------------------------
    # 10. Painel de LED — painéis e módulos
    # ------------------------------------------------------------------
    "led_panels": [
        "LED panel",
        "LED wall panel",
        "LED video wall",
        "LED display panel",
        "indoor LED panel",
        "outdoor LED panel",
        "rental LED wall",
        "LED tile",
        "LED module",
        "P3.9 LED panel",
        "P2.9 LED panel",
        "P2.6 LED panel",
        "P4.8 LED panel",
        "P1.9 LED panel",
    ],

    # ------------------------------------------------------------------
    # 11. Painel de LED — controladoras e processamento
    # ------------------------------------------------------------------
    "led_controllers": [
        "Novastar",
        "Novastar controller",
        "Novastar VX4S",
        "Novastar VX600",
        "Novastar MCTRL300",
        "Novastar A5s",
        "Colorlight controller",
        "LED processor",
        "sending box",
        "receiving card",
    ],

    # ------------------------------------------------------------------
    # 12. Painel de LED — estrutura e acessórios
    # ------------------------------------------------------------------
    "led_accessories": [
        "LED wall road case",
        "LED wall spare parts",
        "LED panel power supply",
        "LED panel receiving card",
        "LED wall frame",
        "LED hanging bar",
        "LED truss mount",
    ],

    # ------------------------------------------------------------------
    # 13. Painel de LED — buscas prontas
    # ------------------------------------------------------------------
    "led_smart": [
        "LED wall lot",
        "video wall lot",
        "LED panel with controller",
        "Novastar lot",
        "rental LED panel",
        "LED wall untested",
        "LED display surplus",
    ],

    # ------------------------------------------------------------------
    # 14. Termos de oportunidade escondida (genéricos)
    # ------------------------------------------------------------------
    "opportunity_terms": [
        "lot",
        "surplus",
        "auction",
        "government surplus",
        "school surplus",
        "university surplus",
        "church audio",
        "broadcast surplus",
        "AV equipment lot",
        "production equipment lot",
        "untested",
        "as-is",
        "for parts",
        "salvage",
    ],

    # ------------------------------------------------------------------
    # 15. Combinações prontas — Allen & Heath
    # ------------------------------------------------------------------
    "combo_allen_heath": [
        "Allen Heath SQ5 with stagebox",
        "Allen Heath SQ6 with case",
        "Allen Heath M500",
        "Allen Heath M1",
        "Allen Heath mixer lot",
        "Allen Heath Dante card",
        "Allen Heath stagebox lot",
        "Allen Heath church audio",
        "Allen Heath untested",
    ],

    # ------------------------------------------------------------------
    # 16. Combinações prontas — Shure Axient
    # ------------------------------------------------------------------
    "combo_shure_axient": [
        "Shure Axient Digital rack",
        "Shure AD4D with antennas",
        "Shure Axient lot",
        "Shure Axient charger",
        "Shure AXT antenna distribution",
        "Shure Axient untested",
    ],

    # ------------------------------------------------------------------
    # 17. Combinações prontas — Luz
    # ------------------------------------------------------------------
    "combo_lighting": [
        "grandMA2 light with case",
        "grandMA2 ultra light",
        "lighting console lot",
        "DMX console with wing",
        "Avolites Tiger Touch case",
    ],

    # ------------------------------------------------------------------
    # 18. Combinações prontas — LED
    # ------------------------------------------------------------------
    "combo_led": [
        "P3.9 LED wall with Novastar",
        "LED panel lot",
        "video wall with controller",
        "rental LED wall case",
        "Novastar controller lot",
    ],

    # ------------------------------------------------------------------
    # 19. Golf Carts — marcas e modelos principais
    # ------------------------------------------------------------------
    "golf_cart_brands": [
        "golf cart",
        "electric golf cart",
        "gas golf cart",
        "Club Car",
        "Club Car Precedent",
        "Club Car DS",
        "Club Car Tempo",
        "EZGO",
        "EZGO TXT",
        "EZGO RXV",
        "Yamaha golf cart",
        "Yamaha Drive",
        "Yamaha G29",
    ],

    # ------------------------------------------------------------------
    # 20. Golf Carts — lotes e frotas
    # ------------------------------------------------------------------
    "golf_cart_fleet": [
        "golf cart lot",
        "golf cart fleet",
        "fleet of golf carts",
        "golf carts lot",
        "golf cart surplus",
        "resort golf carts",
        "golf course equipment",
        "resort fleet golf carts",
        "multiple golf carts",
        "Club Car Precedent lot",
        "EZGO TXT fleet",
        "golf cart fleet auction",
        "resort golf cart surplus",
        "electric golf cart lot",
        "utility cart fleet",
    ],

    # ------------------------------------------------------------------
    # 21. Golf Carts — acessórios e peças
    # ------------------------------------------------------------------
    "golf_cart_accessories": [
        "golf cart batteries",
        "trojan battery",
        "deep cycle battery",
        "golf cart charger",
        "club car charger",
        "ezgo charger",
        "golf cart parts",
        "golf cart motor",
        "golf cart controller",
        "golf cart rear seat kit",
        "golf cart lift kit",
        "lifted golf cart",
        "custom golf cart",
        "golf cart wheels",
        "golf cart body kit",
    ],

    # ------------------------------------------------------------------
    # 22. Golf Carts — industrial e utilitários
    # ------------------------------------------------------------------
    "golf_cart_industrial": [
        "utility cart",
        "work cart",
        "maintenance cart",
        "used golf cart",
        "golf cart auction",
    ],

    # ------------------------------------------------------------------
    # 23. Golf Carts — buscas inteligentes (garimpo)
    # ------------------------------------------------------------------
    "golf_cart_smart": [
        "golf cart untested",
        "golf cart as-is",
        "golf cart needs batteries",
        "golf cart not working",
    ],
}

# ==========================================
# SISTEMA DE PRIORIDADE
# ==========================================
# Grupo A — prioridade máxima (equipamentos de alto valor)
# Grupo B — ótima oportunidade (equipamentos de bom valor)
# Grupo C — garimpo (oportunidades escondidas, itens com defeito)
#
# A prioridade define a ORDEM de execução: Grupo A roda primeiro,
# depois B, depois C. Dentro de cada grupo a rotação é sequencial.

PRIORITY_A = [
    "allen_heath_mixers",
    "shure_axient",
    "lighting_consoles",
    "led_controllers",
    "golf_cart_brands",
    "golf_cart_fleet",
    "combo_allen_heath",
    "combo_shure_axient",
    "combo_lighting",
    "combo_led",
]

PRIORITY_B = [
    "allen_heath_accessories",
    "shure_axient_accessories",
    "lighting_accessories",
    "led_panels",
    "led_accessories",
    "led_smart",
    "lighting_smart",
    "shure_axient_smart",
    "golf_cart_accessories",
    "golf_cart_industrial",
]

PRIORITY_C = [
    "allen_heath_smart",
    "golf_cart_smart",
    "opportunity_terms",
]

# Lista consolidada na ordem de prioridade (usada pelo main.py)
ALL_PRIORITY_GROUPS = [
    ("A", PRIORITY_A),
    ("B", PRIORITY_B),
    ("C", PRIORITY_C),
]

# ==========================================
# FILTROS POR CATEGORIA
# ==========================================
# Preço máximo (USD) por categoria — itens acima são ignorados
MAX_PRICE = {
    "allen_heath_mixers":       15000,
    "allen_heath_accessories":   5000,
    "allen_heath_smart":        12000,
    "shure_axient":             10000,
    "shure_axient_accessories":  3000,
    "shure_axient_smart":        8000,
    "lighting_consoles":        20000,
    "lighting_accessories":      5000,
    "lighting_smart":           15000,
    "led_panels":               25000,
    "led_controllers":           8000,
    "led_accessories":           5000,
    "led_smart":                20000,
    "opportunity_terms":        10000,
    "combo_allen_heath":        15000,
    "combo_shure_axient":       10000,
    "combo_lighting":           20000,
    "combo_led":                25000,
    "golf_cart_brands":         15000,
    "golf_cart_fleet":          50000,
    "golf_cart_accessories":     3000,
    "golf_cart_industrial":      8000,
    "golf_cart_smart":          10000,
}

# Margem mínima de lucro estimada (%) para enviar alerta
MIN_PROFIT_MARGIN = int(os.environ.get("MIN_PROFIT_MARGIN", "30"))

# ==========================================
# CONFIGURAÇÃO DE ROTAÇÃO
# ==========================================
# Número máximo de termos por ciclo de monitoramento (1 hora).
# Isso evita sobrecarga nos sites e mantém o uso de memória baixo.
# Com ~250 termos totais, cada ciclo processa um subconjunto e
# rotaciona para o próximo na hora seguinte.
TERMS_PER_CYCLE = int(os.environ.get("TERMS_PER_CYCLE", "25"))

# Delay (segundos) entre cada requisição para evitar bloqueio
REQUEST_DELAY = int(os.environ.get("REQUEST_DELAY", "3"))

# ==========================================
# COMPATIBILIDADE — lista plana de keywords (legado)
# ==========================================
# Mantida para compatibilidade com código que ainda use config.KEYWORDS
KEYWORDS = []
for _cat_terms in SEARCH_TERMS.values():
    KEYWORDS.extend(_cat_terms)
