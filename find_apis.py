"""
Investigar APIs internas de GovDeals e BidSpotter.
Também investigar JJ Kane /equipment/ com Gravity Forms.
"""
import requests
from bs4 import BeautifulSoup
import re, json, os, sys
sys.path.insert(0, '.')
os.environ['TELEGRAM_TOKEN'] = '123456:ABC'
os.environ['TELEGRAM_CHAT_ID'] = '123456'
os.environ['OPENAI_API_KEY'] = 'test'
import config

s = requests.Session()
s.headers.update(config.HEADERS)

# ============================================================
# 1. GOVDEALS - Procurar API interna no HTML/JS
# ============================================================
print("=" * 60)
print("1. GOVDEALS - Procurar API interna")
print("=" * 60)

# Verificar se o HTML tem referências a API endpoints
r = s.get('https://www.govdeals.com/en/search?q=golf+cart', timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')

# Procurar em scripts inline
for script in soup.find_all('script'):
    text = script.string or ''
    # Procurar URLs de API
    api_matches = re.findall(r'["\'](/api/[^"\']+)["\']', text)
    for m in api_matches:
        print(f"  API endpoint: {m}")
    
    # Procurar fetch/axios calls
    fetch_matches = re.findall(r'fetch\(["\']([^"\']+)["\']', text)
    for m in fetch_matches:
        print(f"  fetch(): {m}")
    
    # Procurar URLs com search
    search_matches = re.findall(r'["\']([^"\']*search[^"\']*)["\']', text, re.IGNORECASE)
    for m in search_matches[:5]:
        if len(m) > 10 and len(m) < 200:
            print(f"  search URL: {m}")

# Procurar em script src
for script in soup.find_all('script', src=True):
    src = script['src']
    if 'chunk' in src or 'main' in src or 'app' in src:
        print(f"  JS bundle: {src[:100]}")

# Tentar GovDeals GraphQL ou REST API
print("\n  Testando endpoints conhecidos...")
test_endpoints = [
    ('https://www.govdeals.com/en/search?q=golf+cart&format=json', 'JSON format'),
    ('https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchtext=golf+cart&rowCount=25&output=json', 'CFM JSON'),
]
for url, name in test_endpoints:
    try:
        r2 = s.get(url, timeout=15)
        print(f"  [{r2.status_code}] {name}: {len(r2.text)} chars")
        ct = r2.headers.get('content-type', '')
        print(f"    Content-Type: {ct}")
        if 'json' in ct:
            print(f"    JSON data found!")
    except Exception as e:
        print(f"  [ERR] {name}: {e}")

# Verificar se GovDeals usa Algolia ou ElasticSearch
r3 = s.get('https://www.govdeals.com/en/search?q=golf+cart', timeout=20)
if 'algolia' in r3.text.lower():
    print("  → ALGOLIA detectado!")
    # Procurar app ID e API key
    algolia_matches = re.findall(r'["\']([A-Z0-9]{10,})["\']', r3.text)
    print(f"  Possíveis Algolia IDs: {algolia_matches[:5]}")

if 'elasticsearch' in r3.text.lower() or 'elastic' in r3.text.lower():
    print("  → ElasticSearch detectado!")

# ============================================================
# 2. BIDSPOTTER - Procurar URL de busca que funciona
# ============================================================
print("\n" + "=" * 60)
print("2. BIDSPOTTER - Procurar URL de busca funcional")
print("=" * 60)

# Testar várias URLs
bidspotter_urls = [
    'https://www.bidspotter.com/en-us/search?query=golf+cart',
    'https://www.bidspotter.com/en-us/search?q=golf+cart',
    'https://www.bidspotter.com/en-gb/search?query=golf+cart',
    'https://www.bidspotter.com/en-us/auction-catalogues?query=golf+cart',
    'https://www.bidspotter.com/en-us/categories',
    'https://www.bidspotter.com/en-us/auctions',
    'https://www.bidspotter.com/en-us',
]

for url in bidspotter_urls:
    try:
        r4 = s.get(url, timeout=15, allow_redirects=True)
        print(f"  [{r4.status_code}] {url[:60]}")
        print(f"    URL final: {r4.url[:80]}")
        if r4.status_code == 200 and 'error' not in r4.url.lower():
            soup4 = BeautifulSoup(r4.text, 'html.parser')
            title4 = soup4.find('title')
            print(f"    Título: {title4.get_text()[:60] if title4 else 'N/A'}")
            # Procurar links de leilão
            lot_links = [l for l in soup4.find_all('a', href=True) if 'lot' in l['href'].lower() or 'auction-catalogue' in l['href'].lower()]
            if lot_links:
                print(f"    Lot links: {len(lot_links)}")
                for l in lot_links[:2]:
                    print(f"      → {l.get_text(strip=True)[:40]} | {l['href'][:60]}")
    except Exception as e:
        print(f"  [ERR] {url[:60]}: {e}")

# Verificar se BidSpotter tem API
print("\n  Testando BidSpotter API...")
api_urls = [
    'https://www.bidspotter.com/api/search?query=golf+cart&limit=20',
    'https://api.bidspotter.com/search?q=golf+cart',
    'https://www.bidspotter.com/api/v1/search?q=golf+cart',
]
for url in api_urls:
    try:
        headers = config.HEADERS.copy()
        headers['Accept'] = 'application/json'
        r5 = s.get(url, timeout=10, headers=headers)
        print(f"  [{r5.status_code}] {url[:60]} ({len(r5.text)} chars)")
        if r5.status_code == 200:
            try:
                data = r5.json()
                print(f"    JSON keys: {list(data.keys())[:5]}")
            except:
                print(f"    Not JSON. First 200 chars: {r5.text[:200]}")
    except Exception as e:
        print(f"  [ERR] {url[:60]}: {e}")

# ============================================================
# 3. JJ KANE - Investigar /equipment/ e Gravity Forms
# ============================================================
print("\n" + "=" * 60)
print("3. JJ KANE - Investigar /equipment/ e busca")
print("=" * 60)

r6 = s.get('https://www.jjkane.com/equipment/', timeout=15)
soup6 = BeautifulSoup(r6.text, 'html.parser')
print(f"  [{r6.status_code}] /equipment/ ({len(r6.text)} chars)")

# Procurar formulários
forms = soup6.find_all('form')
for form in forms:
    action = form.get('action', '')
    method = form.get('method', 'GET')
    inputs = form.find_all('input')
    selects = form.find_all('select')
    print(f"\n  Form: action={action} method={method}")
    for inp in inputs:
        name = inp.get('name', '')
        type_ = inp.get('type', '')
        placeholder = inp.get('placeholder', '')
        if name:
            print(f"    Input: name={name} type={type_} placeholder={placeholder[:30]}")
    for sel in selects:
        name = sel.get('name', '')
        options = sel.find_all('option')
        print(f"    Select: name={name} ({len(options)} options)")
        for opt in options[:5]:
            print(f"      → {opt.get_text(strip=True)[:30]} = {opt.get('value', '')[:30]}")

# Procurar links de equipamentos na página
equip_links = soup6.find_all('a', href=lambda h: h and '/equipment/' in h)
unique_equip = set()
for link in equip_links:
    href = link['href']
    txt = link.get_text(strip=True)
    if txt and len(txt) > 3 and href not in unique_equip and href != '/equipment/':
        unique_equip.add(href)
        if len(unique_equip) <= 10:
            print(f"  Equipment link: {txt[:40]} | {href[:60]}")

# Verificar se JJ Kane tem busca via WordPress REST API
print("\n  Testando WordPress REST API...")
wp_urls = [
    'https://www.jjkane.com/wp-json/wp/v2/posts?search=golf+cart',
    'https://www.jjkane.com/wp-json/wp/v2/pages?search=golf+cart',
    'https://www.jjkane.com/wp-json/gf/v2/forms',
]
for url in wp_urls:
    try:
        r7 = s.get(url, timeout=10)
        print(f"  [{r7.status_code}] {url.split('.com')[1][:50]} ({len(r7.text)} chars)")
        if r7.status_code == 200:
            try:
                data = r7.json()
                if isinstance(data, list):
                    print(f"    Resultados: {len(data)}")
                    for item in data[:3]:
                        title = item.get('title', {})
                        if isinstance(title, dict):
                            title = title.get('rendered', '')
                        print(f"      → {str(title)[:50]}")
                elif isinstance(data, dict):
                    print(f"    Keys: {list(data.keys())[:5]}")
            except:
                pass
    except Exception as e:
        print(f"  [ERR] {url.split('.com')[1][:50]}: {e}")

# Verificar se JJ Kane tem leilões com inventário pesquisável
print("\n  Verificando leilão específico...")
# Pegar primeiro link de leilão
r8 = s.get('https://www.jjkane.com/auctions/', timeout=15)
soup8 = BeautifulSoup(r8.text, 'html.parser')
auction_links = []
for link in soup8.find_all('a', href=True):
    href = link['href']
    if '/auctions/' in href and href != '/auctions/' and href != 'https://www.jjkane.com/auctions/':
        if 'jjkane.com' in href or href.startswith('/'):
            auction_links.append(href)

if auction_links:
    # Visitar primeiro leilão
    first = auction_links[0]
    if first.startswith('/'):
        first = 'https://www.jjkane.com' + first
    print(f"  Visitando: {first}")
    try:
        r9 = s.get(first, timeout=15)
        soup9 = BeautifulSoup(r9.text, 'html.parser')
        print(f"  [{r9.status_code}] ({len(r9.text)} chars)")
        title9 = soup9.find('title')
        print(f"  Título: {title9.get_text()[:60] if title9 else 'N/A'}")
        
        # Procurar links de lotes/itens
        item_links = [l for l in soup9.find_all('a', href=True) if any(k in l['href'].lower() for k in ['lot', 'item', 'equipment'])]
        print(f"  Links de itens: {len(item_links)}")
        for l in item_links[:5]:
            print(f"    → {l.get_text(strip=True)[:40]} | {l['href'][:60]}")
    except Exception as e:
        print(f"  [ERR] {e}")

print("\n✅ Investigação de APIs concluída!")
