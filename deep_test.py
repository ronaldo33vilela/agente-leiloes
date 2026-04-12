"""
Teste profundo de cada scraper com requests reais.
Testa URLs, parsing, filtros e retorno de resultados.
"""
import sys
import os
import json
import time
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['TELEGRAM_TOKEN'] = '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
os.environ['TELEGRAM_CHAT_ID'] = '123456'
os.environ['OPENAI_API_KEY'] = 'test_key'

import config

HEADERS = config.HEADERS.copy()
KEYWORD = "golf cart"

results_log = {}

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_url(name, url, params=None, verify=True):
    """Testa uma URL e retorna (status_code, text_length, soup)"""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(url, params=params, timeout=20, verify=verify)
        print(f"  [{resp.status_code}] {url[:80]}")
        print(f"  Tamanho: {len(resp.text)} chars")
        
        # Verifica se é Cloudflare/bloqueio
        text_lower = resp.text[:2000].lower()
        if 'cloudflare' in text_lower:
            print(f"  ⚠️  CLOUDFLARE detectado!")
        if 'captcha' in text_lower:
            print(f"  ⚠️  CAPTCHA detectado!")
        if 'access denied' in text_lower:
            print(f"  ⚠️  ACCESS DENIED!")
        if 'just a moment' in text_lower:
            print(f"  ⚠️  Cloudflare 'Just a moment' page!")
        if resp.status_code == 403:
            print(f"  ⚠️  403 FORBIDDEN!")
        if resp.status_code == 404:
            print(f"  ⚠️  404 NOT FOUND!")
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            print(f"  Título da página: {title_tag.get_text()[:80]}")
        
        # Contar links
        links = soup.find_all('a', href=True)
        print(f"  Links na página: {len(links)}")
        
        return resp.status_code, len(resp.text), soup
    except Exception as e:
        print(f"  ❌ ERRO: {e}")
        return 0, 0, None

# ============================================================
# TESTE 1: GovDeals
# ============================================================
section("1. GOVDEALS - Teste de URLs")

print("\n--- URL API (AdvSearchResultsNew) ---")
status1, size1, soup1 = test_url(
    "GovDeals API",
    "https://www.govdeals.com/index.cfm",
    params={"fa": "Main.AdvSearchResultsNew", "searchtext": KEYWORD, "rowCount": "25"}
)
if soup1:
    # Procurar links de itens
    item_links = soup1.find_all('a', href=lambda h: h and ('itemid=' in h.lower() or '/en/asset/' in h.lower()))
    print(f"  Links de itens encontrados: {len(item_links)}")
    for link in item_links[:3]:
        print(f"    → {link.get_text(strip=True)[:60]} | {link['href'][:80]}")

print("\n--- URL HTML (/en/search) ---")
status2, size2, soup2 = test_url(
    "GovDeals HTML",
    f"https://www.govdeals.com/en/search?q={KEYWORD.replace(' ', '+')}&sort=closing_soon"
)
if soup2:
    item_links2 = soup2.find_all('a', href=lambda h: h and '/en/asset/' in h)
    print(f"  Links /en/asset/ encontrados: {len(item_links2)}")
    for link in item_links2[:3]:
        print(f"    → {link.get_text(strip=True)[:60]} | {link['href'][:80]}")

print("\n--- Teste do Scraper ---")
try:
    from scrapers.govdeals import GovDealsScraper
    scraper = GovDealsScraper()
    items = scraper.search(KEYWORD)
    print(f"  Scraper retornou: {len(items)} itens")
    for item in items[:3]:
        print(f"    → {item.get('title', 'N/A')[:50]} | ${item.get('price', 0)} | {item.get('link', '')[:60]}")
    results_log['govdeals'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO no scraper: {e}")
    import traceback; traceback.print_exc()
    results_log['govdeals'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# TESTE 2: BidSpotter
# ============================================================
section("2. BIDSPOTTER - Teste de URLs")

print("\n--- URL API (/api/search) ---")
status3, size3, soup3 = test_url(
    "BidSpotter API",
    f"https://www.bidspotter.com/api/search?query={KEYWORD.replace(' ', '+')}&limit=20"
)

print("\n--- URL HTML (/en-us/search) ---")
status4, size4, soup4 = test_url(
    "BidSpotter HTML",
    f"https://www.bidspotter.com/en-us/search?query={KEYWORD.replace(' ', '+')}"
)
if soup4:
    lot_links = soup4.find_all('a', href=lambda h: h and ('lot' in h.lower() or 'auction' in h.lower()))
    print(f"  Links de lotes/auctions: {len(lot_links)}")
    for link in lot_links[:3]:
        print(f"    → {link.get_text(strip=True)[:60]} | {link['href'][:80]}")

print("\n--- Teste do Scraper ---")
try:
    from scrapers.bidspotter import BidSpotterScraper
    scraper = BidSpotterScraper()
    items = scraper.search(KEYWORD)
    print(f"  Scraper retornou: {len(items)} itens")
    for item in items[:3]:
        print(f"    → {item.get('title', 'N/A')[:50]} | ${item.get('price', 0)} | {item.get('link', '')[:60]}")
    results_log['bidspotter'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO no scraper: {e}")
    import traceback; traceback.print_exc()
    results_log['bidspotter'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# TESTE 3: Public Surplus
# ============================================================
section("3. PUBLIC SURPLUS - Teste de URLs")

print("\n--- URL de busca ---")
status5, size5, soup5 = test_url(
    "Public Surplus",
    "https://www.publicsurplus.com/sms/browse/search",
    params={"posting": "y", "keyword": KEYWORD},
    verify=False
)
if soup5:
    auction_links = soup5.find_all('a', href=lambda h: h and '/sms/auction/view' in h)
    print(f"  Links de auction/view: {len(auction_links)}")
    for link in auction_links[:5]:
        txt = link.get_text(strip=True)
        if len(txt) > 5 and 'View Images' not in txt:
            print(f"    → {txt[:60]} | {link['href'][:80]}")

print("\n--- Teste do Scraper ---")
try:
    from scrapers.publicsurplus import PublicSurplusScraper
    scraper = PublicSurplusScraper()
    items = scraper.search(KEYWORD)
    print(f"  Scraper retornou: {len(items)} itens")
    for item in items[:3]:
        print(f"    → {item.get('title', 'N/A')[:50]} | ${item.get('price', 0)} | {item.get('link', '')[:60]}")
    results_log['publicsurplus'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO no scraper: {e}")
    import traceback; traceback.print_exc()
    results_log['publicsurplus'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# TESTE 4: JJ Kane
# ============================================================
section("4. JJ KANE - Teste de URLs")

# Testar várias URLs possíveis
jjkane_urls = [
    ("Homepage", "https://www.jjkane.com/"),
    ("Search", f"https://www.jjkane.com/search?q={KEYWORD.replace(' ', '+')}"),
    ("Inventory", f"https://www.jjkane.com/inventory?keyword={KEYWORD.replace(' ', '+')}"),
    ("Auctions", "https://www.jjkane.com/auctions"),
    ("Equipment", "https://www.jjkane.com/equipment"),
    ("Upcoming", "https://www.jjkane.com/upcoming-auctions"),
]

for name, url in jjkane_urls:
    print(f"\n--- {name} ---")
    status, size, soup = test_url(name, url)
    if soup and size > 1000:
        # Procurar links relevantes
        all_links = soup.find_all('a', href=True)
        relevant = [l for l in all_links if any(k in l['href'].lower() for k in ['item', 'lot', 'equipment', 'auction', 'inventory'])]
        if relevant:
            print(f"  Links relevantes: {len(relevant)}")
            for link in relevant[:3]:
                print(f"    → {link.get_text(strip=True)[:50]} | {link['href'][:80]}")

print("\n--- Teste do Scraper ---")
try:
    from scrapers.jjkane import JJKaneScraper
    scraper = JJKaneScraper()
    items = scraper.search(KEYWORD)
    print(f"  Scraper retornou: {len(items)} itens")
    for item in items[:3]:
        print(f"    → {item.get('title', 'N/A')[:50]} | ${item.get('price', 0)} | {item.get('link', '')[:60]}")
    results_log['jjkane'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO no scraper: {e}")
    import traceback; traceback.print_exc()
    results_log['jjkane'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# TESTE 5: AVGear
# ============================================================
section("5. AVGEAR - Teste de URLs")

print("\n--- Página de leilões ---")
status6, size6, soup6 = test_url("AVGear Auctions", "https://www.avgear.com/pages/auctions")
if soup6:
    # Procurar links externos de leilão
    all_links = soup6.find_all('a', href=True)
    external = [l for l in all_links if any(k in l['href'].lower() for k in ['josephfinn', 'hibid', 'liveauctioneers'])]
    print(f"  Links externos de leilão: {len(external)}")
    for link in external[:5]:
        print(f"    → {link.get_text(strip=True)[:50]} | {link['href'][:80]}")
    
    # Verificar status do leilão
    text = soup6.get_text().lower()
    if 'auction' in text:
        for phrase in ['auction live', 'bidding open', 'auction opens', 'auction closed', 'no active']:
            if phrase in text:
                print(f"  Status detectado: '{phrase}'")

print("\n--- Teste do Scraper ---")
try:
    from scrapers.avgear import AVGearScraper
    scraper = AVGearScraper()
    items = scraper.search(KEYWORD)
    print(f"  Scraper retornou: {len(items)} itens")
    for item in items[:3]:
        print(f"    → {item.get('title', 'N/A')[:50]} | ${item.get('price', 0)} | {item.get('link', '')[:60]}")
    results_log['avgear'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO no scraper: {e}")
    import traceback; traceback.print_exc()
    results_log['avgear'] = f"ERRO: {e}"

# ============================================================
# RESUMO
# ============================================================
section("RESUMO FINAL")
print(f"\nTermo de busca: '{KEYWORD}'")
print(f"\nResultados por plataforma:")
total = 0
for platform, count in results_log.items():
    if isinstance(count, int):
        emoji = "✅" if count > 0 else "❌"
        print(f"  {emoji} {platform}: {count} itens")
        total += count
    else:
        print(f"  ❌ {platform}: {count}")
print(f"\nTotal: {total} itens")

# Salvar log
with open('/home/ubuntu/agente-leiloes/deep_test_results.json', 'w') as f:
    json.dump(results_log, f, indent=2)
print(f"\nResultados salvos em deep_test_results.json")
