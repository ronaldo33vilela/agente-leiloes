"""
Investigação profunda do HTML de cada site para entender a estrutura real.
"""
import requests
from bs4 import BeautifulSoup
import os, sys, re, json
sys.path.insert(0, '.')
os.environ['TELEGRAM_TOKEN'] = '123456:ABC'
os.environ['TELEGRAM_CHAT_ID'] = '123456'
os.environ['OPENAI_API_KEY'] = 'test'
import config

s = requests.Session()
s.headers.update(config.HEADERS)

def save_html(name, html):
    with open(f'/home/ubuntu/agente-leiloes/debug_{name}.html', 'w') as f:
        f.write(html)

# ============================================================
# 1. GOVDEALS - O site usa React/SPA?
# ============================================================
print("=" * 60)
print("1. GOVDEALS - Investigação profunda")
print("=" * 60)

r = s.get('https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchtext=golf+cart&rowCount=25', timeout=20)
save_html('govdeals_api', r.text)
soup = BeautifulSoup(r.text, 'html.parser')

# Verificar se é SPA
body = soup.find('body')
if body:
    # Procurar div#root ou div#app (sinais de SPA)
    root_div = soup.find('div', id='root') or soup.find('div', id='app') or soup.find('div', id='__next')
    if root_div:
        print(f"  SPA detectado! div#{root_div.get('id')}")
    
    # Verificar scripts de framework
    for script in soup.find_all('script', src=True):
        src = script['src']
        if any(fw in src.lower() for fw in ['react', 'angular', 'vue', 'next', 'nuxt']):
            print(f"  Framework JS: {src[:80]}")

# Verificar se tem dados em JSON embutido
for script in soup.find_all('script'):
    text = script.string or ''
    if 'window.__' in text or 'initialState' in text or 'NEXT_DATA' in text:
        print(f"  Dados JSON embutidos encontrados! ({len(text)} chars)")
        # Extrair dados
        if '__NEXT_DATA__' in text:
            print("  → Next.js app com dados SSR!")

# Tentar URL alternativa com API JSON
print("\n  Testando API JSON alternativa...")
api_urls = [
    'https://www.govdeals.com/api/search?q=golf+cart',
    'https://api.govdeals.com/search?q=golf+cart',
    'https://www.govdeals.com/en/api/search?q=golf+cart',
    'https://www.govdeals.com/en/search.json?q=golf+cart',
]
for url in api_urls:
    try:
        r2 = s.get(url, timeout=10)
        print(f"  [{r2.status_code}] {url[:60]} ({len(r2.text)} chars)")
        if r2.status_code == 200 and r2.text.startswith('{'):
            print(f"  → JSON encontrado!")
            data = r2.json()
            print(f"  → Keys: {list(data.keys())[:5]}")
    except Exception as e:
        print(f"  [ERR] {url[:60]}: {e}")

# Tentar a nova URL do GovDeals
print("\n  Testando URLs modernas do GovDeals...")
modern_urls = [
    'https://www.govdeals.com/en/search?q=golf+cart',
    'https://www.govdeals.com/en/search?q=golf+cart&sort=closing_soon',
]
for url in modern_urls:
    r3 = s.get(url, timeout=20)
    soup3 = BeautifulSoup(r3.text, 'html.parser')
    print(f"  [{r3.status_code}] {url[:60]}")
    print(f"  URL final: {r3.url}")
    
    # Verificar se tem resultados renderizados no HTML
    # Procurar padrões comuns de listagem
    cards = soup3.find_all('div', class_=lambda c: c and any(k in c.lower() for k in ['card', 'item', 'result', 'listing', 'product', 'asset']))
    print(f"  Divs tipo card/item/result: {len(cards)}")
    
    # Procurar links de ativos
    asset_links = soup3.find_all('a', href=lambda h: h and ('/asset/' in h or 'itemid=' in h.lower()))
    print(f"  Links de assets: {len(asset_links)}")
    
    # Verificar se é SPA que precisa de JS
    noscript = soup3.find('noscript')
    if noscript:
        print(f"  <noscript> encontrado: {noscript.get_text()[:100]}")

# ============================================================
# 2. BIDSPOTTER
# ============================================================
print("\n" + "=" * 60)
print("2. BIDSPOTTER - Investigação profunda")
print("=" * 60)

r = s.get('https://www.bidspotter.com/en-us/search?query=golf+cart', timeout=20)
save_html('bidspotter', r.text)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"  Status: {r.status_code}, Tamanho: {len(r.text)}")
print(f"  URL final: {r.url}")
title = soup.find('title')
print(f"  Título: {title.get_text() if title else 'N/A'}")

# Verificar se é Cloudflare
if 'cloudflare' in r.text[:5000].lower() or 'just a moment' in r.text[:5000].lower():
    print("  ⚠️ CLOUDFLARE BLOQUEIO!")
    
# Procurar resultados
cards = soup.find_all('div', class_=lambda c: c and any(k in str(c).lower() for k in ['lot', 'result', 'item', 'card', 'listing']))
print(f"  Divs de resultados: {len(cards)}")

lot_links = soup.find_all('a', href=lambda h: h and ('lot' in h.lower() or 'auction-catalogue' in h.lower()))
print(f"  Links de lotes: {len(lot_links)}")
for l in lot_links[:3]:
    print(f"    → {l.get_text(strip=True)[:50]} | {l['href'][:80]}")

# ============================================================
# 3. PUBLIC SURPLUS - Verificar resultados
# ============================================================
print("\n" + "=" * 60)
print("3. PUBLIC SURPLUS - Investigação profunda")
print("=" * 60)

r = s.get('https://www.publicsurplus.com/sms/browse/search?posting=y&keyword=golf+cart', timeout=20, verify=False)
save_html('publicsurplus', r.text)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"  Status: {r.status_code}, Tamanho: {len(r.text)}")

# Contar resultados
auction_links = soup.find_all('a', href=lambda h: h and '/sms/auction/view' in h)
unique_auctions = set()
for link in auction_links:
    txt = link.get_text(strip=True)
    href = link['href']
    if len(txt) > 5 and 'View Images' not in txt:
        auc_match = re.search(r'auc=(\d+)', href)
        if auc_match:
            auc_id = auc_match.group(1)
            if auc_id not in unique_auctions:
                unique_auctions.add(auc_id)
                # Procurar preço próximo
                parent = link.find_parent('tr') or link.find_parent('div')
                price = 'N/A'
                if parent:
                    price_match = re.search(r'\$[\d,]+\.?\d*', parent.get_text())
                    if price_match:
                        price = price_match.group()
                print(f"    → [{auc_id}] {txt[:50]} | {price}")

print(f"  Total de leilões únicos: {len(unique_auctions)}")

# ============================================================
# 4. JJ KANE - Investigar estrutura real
# ============================================================
print("\n" + "=" * 60)
print("4. JJ KANE - Investigação profunda")
print("=" * 60)

r = s.get('https://www.jjkane.com/auctions/', timeout=20)
save_html('jjkane_auctions', r.text)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"  Status: {r.status_code}, Tamanho: {len(r.text)}")

# Procurar links de leilões específicos
auction_links = soup.find_all('a', href=lambda h: h and '/auctions/' in h and h != '/auctions/')
unique_auction_urls = set()
for link in auction_links:
    href = link['href']
    txt = link.get_text(strip=True)
    if txt and len(txt) > 3 and href not in unique_auction_urls:
        unique_auction_urls.add(href)
        if len(unique_auction_urls) <= 10:
            print(f"    → {txt[:50]} | {href[:80]}")

print(f"  Total de links de leilões: {len(unique_auction_urls)}")

# Verificar se tem página de busca de equipamentos
print("\n  Verificando páginas de equipamentos...")
for url in ['https://www.jjkane.com/equipment/', 'https://www.jjkane.com/lots/']:
    try:
        r2 = s.get(url, timeout=10)
        print(f"  [{r2.status_code}] {url}")
        if r2.status_code == 200:
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            # Procurar formulário de busca
            forms = soup2.find_all('form')
            for form in forms:
                action = form.get('action', '')
                if action:
                    print(f"    Form action: {action}")
            # Procurar input de busca
            inputs = soup2.find_all('input', attrs={'type': 'search'}) or soup2.find_all('input', attrs={'name': lambda n: n and 'search' in n.lower()})
            for inp in inputs:
                print(f"    Search input: name={inp.get('name')} placeholder={inp.get('placeholder', '')[:50]}")
    except Exception as e:
        print(f"  [ERR] {url}: {e}")

# Verificar se JJ Kane tem busca via WordPress
print("\n  Testando busca WordPress...")
r3 = s.get('https://www.jjkane.com/?s=golf+cart', timeout=15)
soup3 = BeautifulSoup(r3.text, 'html.parser')
print(f"  [{r3.status_code}] /?s=golf+cart ({len(r3.text)} chars)")
print(f"  URL final: {r3.url}")
title3 = soup3.find('title')
print(f"  Título: {title3.get_text() if title3 else 'N/A'}")

# Procurar resultados
results = soup3.find_all('article') or soup3.find_all('div', class_=lambda c: c and 'result' in str(c).lower())
print(f"  Artigos/resultados: {len(results)}")
for res in results[:5]:
    h = res.find(['h1', 'h2', 'h3', 'h4'])
    if h:
        a = h.find('a')
        if a:
            print(f"    → {a.get_text(strip=True)[:50]} | {a.get('href', '')[:80]}")

print("\n✅ Investigação concluída! Arquivos HTML salvos em debug_*.html")
