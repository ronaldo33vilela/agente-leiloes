"""
Investigação parte 2:
- GovDeals: baixar JS bundle e procurar API endpoints
- BidSpotter: /en-us/auction-catalogues funciona! Investigar busca com filtro
- JJ Kane: /categories/ tem links de equipamentos, investigar
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
# 1. GOVDEALS - Baixar JS bundle e procurar API
# ============================================================
print("=" * 60)
print("1. GOVDEALS - Analisar JS bundle")
print("=" * 60)

r = s.get('https://www.govdeals.com/en/search?q=golf+cart', timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')

# Encontrar JS bundles
for script in soup.find_all('script', src=True):
    src = script['src']
    if 'main' in src or 'app' in src or 'chunk' in src:
        full_url = src if src.startswith('http') else f"https://www.govdeals.com{src}"
        print(f"  Baixando: {full_url[:80]}")
        try:
            r2 = s.get(full_url, timeout=15)
            js_text = r2.text
            print(f"  Tamanho: {len(js_text)} chars")
            
            # Procurar API endpoints
            api_patterns = [
                r'["\'](/api/[^"\']+)["\']',
                r'["\']([^"\']*graphql[^"\']*)["\']',
                r'["\']([^"\']*search[^"\']*api[^"\']*)["\']',
                r'["\']([^"\']*algolia[^"\']*)["\']',
                r'baseURL[:\s]*["\']([^"\']+)["\']',
                r'apiUrl[:\s]*["\']([^"\']+)["\']',
                r'endpoint[:\s]*["\']([^"\']+)["\']',
            ]
            for pattern in api_patterns:
                matches = re.findall(pattern, js_text, re.IGNORECASE)
                for m in matches[:3]:
                    if len(m) > 5 and len(m) < 200:
                        print(f"    API: {m}")
            
            # Procurar Algolia
            if 'algolia' in js_text.lower():
                print("  → ALGOLIA encontrado no JS!")
                # Procurar appId e apiKey
                app_id = re.findall(r'applicationId["\s:]+["\']([A-Z0-9]+)["\']', js_text)
                api_key = re.findall(r'apiKey["\s:]+["\']([a-f0-9]+)["\']', js_text)
                if app_id:
                    print(f"    Algolia App ID: {app_id[0]}")
                if api_key:
                    print(f"    Algolia API Key: {api_key[0][:20]}...")
                    
                # Procurar index name
                index_names = re.findall(r'indexName["\s:]+["\']([^"\']+)["\']', js_text)
                for idx in index_names[:5]:
                    print(f"    Algolia Index: {idx}")
            
            # Procurar qualquer URL com /search ou /assets
            url_matches = re.findall(r'["\']https?://[^"\']*(?:search|asset|item|listing)[^"\']*["\']', js_text, re.IGNORECASE)
            for m in url_matches[:5]:
                print(f"    URL: {m}")
                
        except Exception as e:
            print(f"  [ERR] {e}")

# ============================================================
# 2. BIDSPOTTER - Investigar auction-catalogues com busca
# ============================================================
print("\n" + "=" * 60)
print("2. BIDSPOTTER - auction-catalogues com filtro de busca")
print("=" * 60)

# A página /en-us/auction-catalogues funciona e tem 2007 links!
# Verificar se tem filtro de busca
bidspotter_search_urls = [
    'https://www.bidspotter.com/en-us/auction-catalogues/search-filter?query=golf+cart',
    'https://www.bidspotter.com/en-us/auction-catalogues?query=golf+cart',
    'https://www.bidspotter.com/en-us/auction-catalogues?search=golf+cart',
    'https://www.bidspotter.com/en-us/auction-catalogues/search-filter?SearchText=golf+cart',
    'https://www.bidspotter.com/en-us/featured-lots?query=golf+cart',
]

for url in bidspotter_search_urls:
    try:
        r3 = s.get(url, timeout=15)
        soup3 = BeautifulSoup(r3.text, 'html.parser')
        print(f"\n  [{r3.status_code}] {url.split('.com')[1][:60]}")
        print(f"  URL final: {r3.url[:80]}")
        title = soup3.find('title')
        print(f"  Título: {title.get_text()[:60] if title else 'N/A'}")
        
        # Contar links de lotes
        lot_links = [l for l in soup3.find_all('a', href=True) if '/lot-details/' in l['href'].lower() or '/lot/' in l['href'].lower()]
        if lot_links:
            print(f"  Lot links: {len(lot_links)}")
            for l in lot_links[:3]:
                txt = l.get_text(strip=True)
                if txt and len(txt) > 3:
                    print(f"    → {txt[:50]} | {l['href'][:60]}")
    except Exception as e:
        print(f"  [ERR] {url.split('.com')[1][:60]}: {e}")

# Investigar a homepage para entender a busca
print("\n  Investigando busca na homepage...")
r4 = s.get('https://www.bidspotter.com/en-us', timeout=15)
soup4 = BeautifulSoup(r4.text, 'html.parser')

# Procurar formulários de busca
forms = soup4.find_all('form')
for form in forms:
    action = form.get('action', '')
    inputs = form.find_all('input')
    if any('search' in str(inp).lower() for inp in inputs):
        print(f"  Search form: action={action}")
        for inp in inputs:
            name = inp.get('name', '')
            if name:
                print(f"    Input: {name} = {inp.get('placeholder', '')[:30]}")

# Procurar em scripts
for script in soup4.find_all('script'):
    text = script.string or ''
    if 'search' in text.lower() and ('url' in text.lower() or 'endpoint' in text.lower()):
        # Procurar URLs de busca
        search_urls = re.findall(r'["\']([^"\']*search[^"\']*)["\']', text, re.IGNORECASE)
        for u in search_urls[:5]:
            if len(u) > 10 and len(u) < 200 and ('/' in u or 'http' in u):
                print(f"  Search URL in JS: {u}")

# ============================================================
# 3. JJ KANE - Investigar /categories/ e leilões ativos
# ============================================================
print("\n" + "=" * 60)
print("3. JJ KANE - Investigar categorias e leilões")
print("=" * 60)

# Verificar se tem página de categorias com itens
r5 = s.get('https://www.jjkane.com/categories/golf-carts', timeout=15)
print(f"  [{r5.status_code}] /categories/golf-carts")
if r5.status_code == 200:
    soup5 = BeautifulSoup(r5.text, 'html.parser')
    title5 = soup5.find('title')
    print(f"  Título: {title5.get_text()[:60] if title5 else 'N/A'}")

# Testar outras categorias
categories = ['golf-carts', 'vehicles', 'heavy-equipment', 'trailers', 'trucks']
for cat in categories:
    try:
        r6 = s.get(f'https://www.jjkane.com/categories/{cat}', timeout=10)
        print(f"  [{r6.status_code}] /categories/{cat}")
        if r6.status_code == 200:
            soup6 = BeautifulSoup(r6.text, 'html.parser')
            # Contar itens
            items = soup6.find_all('div', class_=lambda c: c and any(k in str(c).lower() for k in ['item', 'lot', 'product', 'card']))
            links = [l for l in soup6.find_all('a', href=True) if '/lot/' in l['href'] or '/item/' in l['href']]
            print(f"    Items divs: {len(items)}, Item links: {len(links)}")
    except Exception as e:
        print(f"  [ERR] /categories/{cat}: {e}")

# Verificar buy-now
print("\n  Verificando Buy Now...")
r7 = s.get('https://www.jjkane.com/buy-now-items/', timeout=15)
print(f"  [{r7.status_code}] /buy-now-items/ ({len(r7.text)} chars)")
if r7.status_code == 200:
    soup7 = BeautifulSoup(r7.text, 'html.parser')
    title7 = soup7.find('title')
    print(f"  Título: {title7.get_text()[:60] if title7 else 'N/A'}")
    # Procurar itens
    all_links = soup7.find_all('a', href=True)
    buy_links = [l for l in all_links if 'buy-now' in l['href'] and l['href'] != '/buy-now-items/']
    print(f"  Buy Now links: {len(buy_links)}")
    for l in buy_links[:5]:
        print(f"    → {l.get_text(strip=True)[:40]} | {l['href'][:60]}")

print("\n✅ Investigação parte 2 concluída!")
