"""
Investigação parte 7:
- BidSpotter: 318 divs com 'lot' na classe! Extrair dados
- GovDeals: API retorna 406 - precisa headers corretos
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
# 1. BIDSPOTTER - Extrair dados das 318 divs com 'lot'
# ============================================================
print("=" * 60)
print("1. BIDSPOTTER - Extrair dados das divs 'lot'")
print("=" * 60)

r = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=30)
soup = BeautifulSoup(r.text, 'html.parser')

# Encontrar divs com 'lot' na classe
lot_divs = soup.find_all('div', class_=lambda c: c and 'lot' in str(c).lower())
print(f"  Total divs com 'lot': {len(lot_divs)}")

# Analisar classes
classes_found = set()
for div in lot_divs[:20]:
    cls = ' '.join(div.get('class', []))
    classes_found.add(cls)
print(f"\n  Classes únicas:")
for cls in sorted(classes_found):
    print(f"    {cls}")

# Pegar primeira div e analisar estrutura
if lot_divs:
    first = lot_divs[0]
    print(f"\n  Primeira div (classe: {' '.join(first.get('class', []))}):")
    print(f"  HTML: {str(first)[:500]}")
    
    # Procurar links dentro
    links = first.find_all('a', href=True)
    for l in links:
        print(f"    Link: {l.get_text(strip=True)[:40]} | {l['href'][:60]}")
    
    # Procurar imagens
    imgs = first.find_all('img')
    for img in imgs:
        print(f"    Img: alt={img.get('alt', '')[:30]} src={img.get('src', '')[:50]}")

# Procurar padrão de links de lotes
all_links = soup.find_all('a', href=True)
lot_link_patterns = set()
for l in all_links:
    href = l['href']
    if 'lot' in href.lower():
        # Extrair padrão
        lot_link_patterns.add(href[:60])

print(f"\n  Padrões de links com 'lot': {len(lot_link_patterns)}")
for p in sorted(lot_link_patterns)[:20]:
    print(f"    {p}")

# Procurar dados estruturados
# Verificar se tem data-attributes
elements_with_data = soup.find_all(attrs={"data-lot-id": True})
print(f"\n  Elementos com data-lot-id: {len(elements_with_data)}")

elements_with_data2 = soup.find_all(attrs=lambda attrs: attrs and any('lot' in str(k).lower() for k in attrs.keys()))
print(f"  Elementos com data-*lot*: {len(elements_with_data2)}")
for el in elements_with_data2[:3]:
    lot_attrs = {k: v for k, v in el.attrs.items() if 'lot' in k.lower()}
    print(f"    {lot_attrs}")

# ============================================================
# 2. GOVDEALS - Tentar API com headers Angular/React
# ============================================================
print("\n" + "=" * 60)
print("2. GOVDEALS - API com headers corretos")
print("=" * 60)

# O 406 "Not Acceptable" sugere que precisa de Accept header específico
headers_variants = [
    {'Accept': 'application/json', 'Content-Type': 'application/json'},
    {'Accept': 'application/json, text/plain, */*', 'X-Requested-With': 'XMLHttpRequest'},
    {'Accept': '*/*', 'X-Requested-With': 'XMLHttpRequest'},
    {'Accept': 'application/json', 'Origin': 'https://www.govdeals.com', 'Referer': 'https://www.govdeals.com/en/search?q=golf+cart'},
]

for i, extra_headers in enumerate(headers_variants):
    h = config.HEADERS.copy()
    h.update(extra_headers)
    try:
        r2 = requests.get('https://www.govdeals.com/api/search/assets?q=golf+cart', headers=h, timeout=10)
        ct = r2.headers.get('content-type', '')
        print(f"  Variante {i+1}: [{r2.status_code}] {ct[:30]} ({len(r2.text)} chars)")
        if r2.status_code == 200 and 'json' in ct:
            data = r2.json()
            print(f"    SUCESSO! Keys: {list(data.keys())[:5]}")
        elif r2.status_code == 200:
            print(f"    Body: {r2.text[:200]}")
    except Exception as e:
        print(f"  Variante {i+1}: [ERR] {str(e)[:50]}")

# Tentar POST
print("\n  Tentando POST...")
try:
    h = config.HEADERS.copy()
    h['Accept'] = 'application/json'
    h['Content-Type'] = 'application/json'
    h['Origin'] = 'https://www.govdeals.com'
    h['Referer'] = 'https://www.govdeals.com/en/search?q=golf+cart'
    
    payload = {"query": "golf cart", "page": 1, "pageSize": 25}
    r3 = requests.post('https://www.govdeals.com/api/search/assets', headers=h, json=payload, timeout=10)
    print(f"  POST: [{r3.status_code}] {r3.headers.get('content-type', '')[:30]} ({len(r3.text)} chars)")
    if r3.status_code == 200:
        print(f"    Body: {r3.text[:300]}")
except Exception as e:
    print(f"  POST: [ERR] {str(e)[:50]}")

print("\n✅ Investigação parte 7 concluída!")
