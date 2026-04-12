"""
Investigação parte 4:
- BidSpotter: /en-us/search-results?searchTerm=golf+cart
- JJ Kane: Proxibid + /categories/motorcycles-atvs-golf-and-yard-carts
- GovDeals: Tentar acessar JS bundle com URL correta
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
# 1. BIDSPOTTER - search-results
# ============================================================
print("=" * 60)
print("1. BIDSPOTTER - /en-us/search-results?searchTerm=golf+cart")
print("=" * 60)

r = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"  [{r.status_code}] ({len(r.text)} chars)")
print(f"  URL final: {r.url[:80]}")
title = soup.find('title')
print(f"  Título: {title.get_text()[:60] if title else 'N/A'}")

# Verificar conteúdo
if r.status_code == 200 and 'error' not in r.url.lower():
    # Procurar todos os links
    all_links = soup.find_all('a', href=True)
    print(f"  Total links: {len(all_links)}")
    
    # Links de lotes
    lot_links = [l for l in all_links if any(k in l['href'].lower() for k in ['lot-details', '/lot/', 'auction-catalogue'])]
    print(f"  Lot/auction links: {len(lot_links)}")
    for l in lot_links[:5]:
        txt = l.get_text(strip=True)
        if txt:
            print(f"    → {txt[:50]} | {l['href'][:70]}")
    
    # Verificar se é SPA
    noscript = soup.find('noscript')
    if noscript:
        print(f"  <noscript>: {noscript.get_text()[:100]}")
    
    # Procurar dados JSON embutidos
    for script in soup.find_all('script'):
        text = script.string or ''
        if len(text) > 100 and ('lot' in text.lower() or 'result' in text.lower() or 'search' in text.lower()):
            print(f"  Script com dados ({len(text)} chars): {text[:200]}")
    
    # Salvar
    with open('/home/ubuntu/agente-leiloes/debug_bidspotter_searchresults.html', 'w') as f:
        f.write(r.text)

# ============================================================
# 2. JJ KANE - Categoria de Golf Carts
# ============================================================
print("\n" + "=" * 60)
print("2. JJ KANE - /categories/motorcycles-atvs-golf-and-yard-carts")
print("=" * 60)

r2 = s.get('https://www.jjkane.com/categories/motorcycles-atvs-golf-and-yard-carts', timeout=15)
soup2 = BeautifulSoup(r2.text, 'html.parser')
print(f"  [{r2.status_code}] ({len(r2.text)} chars)")
title2 = soup2.find('title')
print(f"  Título: {title2.get_text()[:60] if title2 else 'N/A'}")

if r2.status_code == 200:
    # Procurar itens/lotes
    all_links = soup2.find_all('a', href=True)
    
    # Procurar links de itens
    for link in all_links:
        href = link['href']
        txt = link.get_text(strip=True)
        if txt and len(txt) > 5:
            if any(k in href.lower() for k in ['lot', 'item', 'detail', 'equipment']):
                print(f"  Item: {txt[:50]} | {href[:70]}")
    
    # Procurar divs com conteúdo de itens
    # Verificar se tem listagem de itens
    body_text = soup2.get_text()
    if 'golf' in body_text.lower():
        # Encontrar seções com "golf"
        lines = body_text.split('\n')
        for i, line in enumerate(lines):
            if 'golf' in line.lower() and len(line.strip()) > 10:
                print(f"  Texto com 'golf': {line.strip()[:80]}")
    
    # Procurar imagens de itens
    imgs = soup2.find_all('img', alt=True)
    for img in imgs:
        alt = img.get('alt', '')
        if alt and len(alt) > 5 and any(k in alt.lower() for k in ['golf', 'cart', 'vehicle', 'lot']):
            print(f"  Img: {alt[:50]}")
    
    with open('/home/ubuntu/agente-leiloes/debug_jjkane_golf.html', 'w') as f:
        f.write(r2.text)

# ============================================================
# 3. JJ KANE - Proxibid
# ============================================================
print("\n" + "=" * 60)
print("3. JJ KANE - Proxibid")
print("=" * 60)

r3 = s.get('https://jjkane.proxibid.com/', timeout=15)
print(f"  [{r3.status_code}] jjkane.proxibid.com ({len(r3.text)} chars)")
soup3 = BeautifulSoup(r3.text, 'html.parser')
title3 = soup3.find('title')
print(f"  Título: {title3.get_text()[:60] if title3 else 'N/A'}")

# Procurar leilões ativos
for link in soup3.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if txt and len(txt) > 5 and any(k in href.lower() for k in ['auction', 'catalog', 'lot']):
        print(f"  → {txt[:50]} | {href[:70]}")

# ============================================================
# 4. GOVDEALS - JS bundle com URL correta
# ============================================================
print("\n" + "=" * 60)
print("4. GOVDEALS - JS bundle")
print("=" * 60)

r4 = s.get('https://www.govdeals.com/en/search?q=golf+cart', timeout=20)
soup4 = BeautifulSoup(r4.text, 'html.parser')

for script in soup4.find_all('script', src=True):
    src = script['src']
    if src.startswith('/'):
        full_url = f"https://www.govdeals.com{src}"
    elif src.startswith('http'):
        full_url = src
    else:
        full_url = f"https://www.govdeals.com/{src}"
    
    print(f"  Script: {full_url[:80]}")
    
    if 'main' in src.lower():
        try:
            r5 = s.get(full_url, timeout=15)
            js = r5.text
            print(f"  → Tamanho: {len(js)} chars")
            
            # Procurar API
            api_urls = re.findall(r'["\']https?://[^"\']+["\']', js)
            for u in api_urls:
                u = u.strip('"\'')
                if any(k in u.lower() for k in ['api', 'search', 'graphql', 'algolia']):
                    print(f"    URL: {u[:100]}")
            
            # Procurar /api/ paths
            api_paths = re.findall(r'["\'](/api/[^"\']+)["\']', js)
            for p in set(api_paths):
                print(f"    Path: {p}")
            
            # Procurar algolia
            if 'algolia' in js.lower():
                print("  → ALGOLIA!")
                # Procurar configuração
                algolia_config = re.findall(r'(?:appId|applicationId|ALGOLIA_APP_ID)["\s:=]+["\']([^"\']+)["\']', js, re.IGNORECASE)
                algolia_key = re.findall(r'(?:apiKey|searchKey|ALGOLIA_SEARCH_KEY)["\s:=]+["\']([^"\']+)["\']', js, re.IGNORECASE)
                algolia_index = re.findall(r'(?:indexName|ALGOLIA_INDEX)["\s:=]+["\']([^"\']+)["\']', js, re.IGNORECASE)
                print(f"    App IDs: {algolia_config}")
                print(f"    Keys: {algolia_key}")
                print(f"    Indices: {algolia_index}")
        except Exception as e:
            print(f"  [ERR] {e}")

print("\n✅ Investigação parte 4 concluída!")
