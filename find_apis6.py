"""
Investigação parte 6:
- GovDeals: testar /api/search/assets e outros endpoints
- BidSpotter: extrair dados de search-results (funciona!)
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
# 1. GOVDEALS - Testar API endpoints
# ============================================================
print("=" * 60)
print("1. GOVDEALS - Testar API endpoints")
print("=" * 60)

govdeals_apis = [
    '/api/search/assets?q=golf+cart',
    '/api/assets/search?q=golf+cart',
    '/api/search?q=golf+cart',
    '/api/assets?q=golf+cart',
    '/api/search/assets?query=golf+cart',
    '/api/v1/search?q=golf+cart',
    '/api/v1/assets/search?q=golf+cart',
    '/api/search/assets?searchtext=golf+cart',
    '/api/search/assets?keyword=golf+cart',
]

for path in govdeals_apis:
    url = f"https://www.govdeals.com{path}"
    try:
        headers = config.HEADERS.copy()
        headers['Accept'] = 'application/json'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        r = s.get(url, timeout=10, headers=headers)
        ct = r.headers.get('content-type', '')
        print(f"  [{r.status_code}] {path[:50]} → {ct[:30]} ({len(r.text)} chars)")
        if 'json' in ct:
            try:
                data = r.json()
                if isinstance(data, dict):
                    print(f"    Keys: {list(data.keys())[:5]}")
                    # Verificar se tem resultados
                    for key in ['results', 'items', 'assets', 'data', 'hits']:
                        if key in data:
                            val = data[key]
                            if isinstance(val, list):
                                print(f"    {key}: {len(val)} itens")
                                if val:
                                    print(f"    Primeiro: {json.dumps(val[0])[:200]}")
                elif isinstance(data, list):
                    print(f"    Lista: {len(data)} itens")
            except:
                pass
    except Exception as e:
        print(f"  [ERR] {path[:50]}: {str(e)[:50]}")

# ============================================================
# 2. BIDSPOTTER - Extrair dados de search-results
# ============================================================
print("\n" + "=" * 60)
print("2. BIDSPOTTER - Extrair dados de search-results")
print("=" * 60)

r2 = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=20)
soup2 = BeautifulSoup(r2.text, 'html.parser')
print(f"  [{r2.status_code}] ({len(r2.text)} chars)")

# Procurar estrutura de resultados
# Procurar divs com classe que contenha 'lot' ou 'result'
lot_divs = soup2.find_all('div', class_=lambda c: c and ('lot' in str(c).lower()))
print(f"  Divs com 'lot' na classe: {len(lot_divs)}")

# Procurar links com lot-details
lot_links = soup2.find_all('a', href=lambda h: h and 'lot-details' in h.lower())
print(f"  Links com lot-details: {len(lot_links)}")
for l in lot_links[:5]:
    txt = l.get_text(strip=True)
    href = l['href']
    print(f"    → {txt[:50]} | {href[:70]}")

# Procurar links com /auction-catalogues/
catalog_links = soup2.find_all('a', href=lambda h: h and '/auction-catalogues/' in h and 'lot-details' in h)
print(f"\n  Links de catálogo com lot-details: {len(catalog_links)}")
seen = set()
for l in catalog_links:
    txt = l.get_text(strip=True)
    href = l['href']
    if txt and len(txt) > 3 and txt not in seen:
        seen.add(txt)
        # Procurar preço próximo
        parent = l.find_parent('div') or l.find_parent('li')
        price = 'N/A'
        if parent:
            price_match = re.search(r'[\$£€][\d,]+\.?\d*', parent.get_text())
            if price_match:
                price = price_match.group()
        if len(seen) <= 15:
            print(f"    → {txt[:50]} | {price} | {href[:60]}")

print(f"\n  Total de lotes únicos: {len(seen)}")

# Verificar se há paginação
pagination = soup2.find_all('a', href=lambda h: h and 'page' in str(h).lower())
print(f"  Links de paginação: {len(pagination)}")

# Procurar dados JSON embutidos (pode ter __NEXT_DATA__ ou similar)
for script in soup2.find_all('script', type='application/json'):
    text = script.string or ''
    if len(text) > 100:
        print(f"\n  JSON embutido ({len(text)} chars)")
        try:
            data = json.loads(text)
            print(f"    Keys: {list(data.keys())[:5] if isinstance(data, dict) else 'list'}")
        except:
            print(f"    Não é JSON válido")

# Procurar dados em script tags normais
for script in soup2.find_all('script'):
    text = script.string or ''
    if 'searchResults' in text or 'lotData' in text or '"lots"' in text:
        print(f"\n  Script com dados de busca ({len(text)} chars)")
        # Extrair JSON
        json_match = re.search(r'(\{[^}]{100,})', text)
        if json_match:
            print(f"    Início: {json_match.group()[:200]}")

print("\n✅ Investigação parte 6 concluída!")
