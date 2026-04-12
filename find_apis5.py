"""
Investigação parte 5:
- GovDeals: procurar API no JS bundle de 1.2MB
- JJ Kane Proxibid: buscar catálogos de leilão
- BidSpotter: verificar search-results
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
# 1. GOVDEALS - Procurar API no JS bundle
# ============================================================
print("=" * 60)
print("1. GOVDEALS - Procurar API no JS de 1.2MB")
print("=" * 60)

r = s.get('https://www.govdeals.com/main.1775144873739.56c7a234a14d900f.js', timeout=20)
js = r.text
print(f"  JS bundle: {len(js)} chars")

# Procurar /api/ paths
api_paths = set(re.findall(r'["\'](/api/[^"\']{3,60})["\']', js))
print(f"\n  API paths encontrados: {len(api_paths)}")
for p in sorted(api_paths):
    print(f"    {p}")

# Procurar URLs completas com domínio
full_urls = set(re.findall(r'["\'](https?://[^"\']{10,100})["\']', js))
api_full = [u for u in full_urls if any(k in u.lower() for k in ['api', 'search', 'graphql', 'elastic', 'algolia'])]
print(f"\n  URLs com API/search: {len(api_full)}")
for u in sorted(api_full):
    print(f"    {u}")

# Procurar environment/config
env_matches = re.findall(r'(?:environment|apiUrl|baseUrl|apiBase|API_URL|BASE_URL)["\s:=]+["\']([^"\']+)["\']', js, re.IGNORECASE)
print(f"\n  Environment/config URLs: {len(env_matches)}")
for m in env_matches:
    print(f"    {m}")

# Procurar padrões de busca
search_patterns = re.findall(r'(?:searchUrl|searchEndpoint|searchApi)["\s:=]+["\']([^"\']+)["\']', js, re.IGNORECASE)
print(f"\n  Search endpoints: {len(search_patterns)}")
for p in search_patterns:
    print(f"    {p}")

# ============================================================
# 2. GOVDEALS - Testar APIs encontradas
# ============================================================
print("\n" + "=" * 60)
print("2. GOVDEALS - Testar APIs encontradas")
print("=" * 60)

# Testar cada API path encontrado com busca
for path in sorted(api_paths):
    if 'search' in path.lower() or 'asset' in path.lower() or 'item' in path.lower():
        url = f"https://www.govdeals.com{path}"
        # Substituir placeholders
        if '{' in url:
            continue
        try:
            r2 = s.get(url, timeout=10, params={'q': 'golf cart', 'query': 'golf cart', 'search': 'golf cart'})
            ct = r2.headers.get('content-type', '')
            print(f"  [{r2.status_code}] {path} → {ct[:30]} ({len(r2.text)} chars)")
            if 'json' in ct:
                try:
                    data = r2.json()
                    print(f"    Keys: {list(data.keys())[:5] if isinstance(data, dict) else f'list[{len(data)}]'}")
                except:
                    pass
        except Exception as e:
            print(f"  [ERR] {path}: {e}")

# ============================================================
# 3. JJ KANE Proxibid - Buscar catálogo
# ============================================================
print("\n" + "=" * 60)
print("3. JJ KANE Proxibid - Buscar em catálogos")
print("=" * 60)

# Tentar acessar um catálogo de leilão
catalog_urls = [
    'https://jjkane.proxibid.com/JJ-Kane-Auctions/4-28-Southeast-Regional-Auction-Day-1-Ring-2/event-catalog/293310',
    'https://jjkane.proxibid.com/JJ-Kane-Auctions/4-28-Northern-California-Auction-Ring-2/event-catalog/293304',
]

for url in catalog_urls:
    try:
        r3 = s.get(url, timeout=15)
        soup3 = BeautifulSoup(r3.text, 'html.parser')
        print(f"\n  [{r3.status_code}] {url.split('proxibid.com')[1][:60]}")
        title = soup3.find('title')
        print(f"  Título: {title.get_text()[:60] if title else 'N/A'}")
        
        # Procurar itens/lotes no catálogo
        lot_elements = soup3.find_all(['div', 'tr', 'li'], class_=lambda c: c and any(k in str(c).lower() for k in ['lot', 'item', 'catalog']))
        print(f"  Lot elements: {len(lot_elements)}")
        
        # Procurar links de lotes
        lot_links = [l for l in soup3.find_all('a', href=True) if 'lot' in l['href'].lower() or 'item' in l['href'].lower()]
        print(f"  Lot links: {len(lot_links)}")
        for l in lot_links[:5]:
            txt = l.get_text(strip=True)
            if txt and len(txt) > 3:
                print(f"    → {txt[:50]} | {l['href'][:60]}")
        
        # Procurar texto com "golf" no catálogo
        text = soup3.get_text()
        if 'golf' in text.lower():
            lines = text.split('\n')
            for line in lines:
                if 'golf' in line.lower() and len(line.strip()) > 5:
                    print(f"  Golf item: {line.strip()[:80]}")
        
        # Verificar se é SPA
        for script in soup3.find_all('script'):
            st = script.string or ''
            if 'catalog' in st.lower() or 'lot' in st.lower():
                if len(st) > 100:
                    print(f"  JS com dados de catálogo: {st[:200]}")
                    
    except Exception as e:
        print(f"  [ERR] {e}")

# ============================================================
# 4. BIDSPOTTER - search-results detalhado
# ============================================================
print("\n" + "=" * 60)
print("4. BIDSPOTTER - search-results detalhado")
print("=" * 60)

r4 = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=20)
soup4 = BeautifulSoup(r4.text, 'html.parser')
print(f"  [{r4.status_code}] ({len(r4.text)} chars)")
print(f"  URL final: {r4.url[:80]}")

# Verificar se tem conteúdo
body_text = soup4.get_text()
if 'golf' in body_text.lower():
    lines = body_text.split('\n')
    golf_lines = [l.strip() for l in lines if 'golf' in l.lower() and len(l.strip()) > 5]
    print(f"  Linhas com 'golf': {len(golf_lines)}")
    for l in golf_lines[:10]:
        print(f"    → {l[:80]}")
else:
    print("  Nenhuma menção a 'golf' no texto!")
    # Verificar se é SPA
    scripts = soup4.find_all('script')
    print(f"  Scripts: {len(scripts)}")
    for script in scripts:
        src = script.get('src', '')
        if src:
            print(f"    src: {src[:60]}")

print("\n✅ Investigação parte 5 concluída!")
