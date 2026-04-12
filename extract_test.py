"""
Teste de extração real de dados:
- BidSpotter: extrair lotes com data-lot-id
- GovDeals: tentar abordagem alternativa (RSS, sitemap, ou scraping direto)
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
# 1. BIDSPOTTER - Extrair lotes com data-lot-id
# ============================================================
print("=" * 60)
print("1. BIDSPOTTER - Extrair lotes com data-lot-id")
print("=" * 60)

r = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=30)
soup = BeautifulSoup(r.text, 'html.parser')

# Encontrar elementos com data-lot-id
lot_elements = soup.find_all(attrs={"data-lot-id": True})
print(f"  Elementos com data-lot-id: {len(lot_elements)}")

items = []
for el in lot_elements[:20]:
    lot_id = el.get('data-lot-id', '')
    
    # Extrair título
    title = ''
    title_el = el.find(['h2', 'h3', 'h4', 'a'])
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        title = el.get_text(strip=True)[:100]
    
    # Extrair link
    link = ''
    link_el = el.find('a', href=True)
    if link_el:
        link = link_el['href']
        if link.startswith('/'):
            link = f"https://www.bidspotter.com{link}"
    
    # Extrair preço
    price = 'N/A'
    price_match = re.search(r'[\$£€][\d,]+\.?\d*', el.get_text())
    if price_match:
        price = price_match.group()
    
    # Extrair imagem
    img = ''
    img_el = el.find('img', src=True)
    if img_el:
        img = img_el.get('alt', '')[:50]
    
    if title and len(title) > 3:
        items.append({
            'lot_id': lot_id,
            'title': title[:80],
            'link': link[:80],
            'price': price,
            'img_alt': img
        })
        print(f"  [{lot_id}] {title[:60]}")
        print(f"    Link: {link[:70]}")
        print(f"    Preço: {price}")

print(f"\n  Total de itens extraídos: {len(items)}")

# Verificar se os itens são relevantes para "golf cart"
golf_items = [i for i in items if 'golf' in i['title'].lower() or 'cart' in i['title'].lower()]
print(f"  Itens com 'golf' ou 'cart': {len(golf_items)}")
for item in golf_items[:10]:
    print(f"    → {item['title'][:60]} | {item['price']}")

# ============================================================
# 2. GOVDEALS - Tentar abordagens alternativas
# ============================================================
print("\n" + "=" * 60)
print("2. GOVDEALS - Abordagens alternativas")
print("=" * 60)

# Tentar RSS feed
print("\n--- RSS Feed ---")
rss_urls = [
    'https://www.govdeals.com/rss',
    'https://www.govdeals.com/feed',
    'https://www.govdeals.com/en/rss',
    'https://www.govdeals.com/en/feed',
]
for url in rss_urls:
    try:
        r2 = s.get(url, timeout=10)
        print(f"  [{r2.status_code}] {url.split('.com')[1]} ({len(r2.text)} chars)")
    except Exception as e:
        print(f"  [ERR] {url.split('.com')[1]}: {str(e)[:40]}")

# Tentar sitemap
print("\n--- Sitemap ---")
try:
    r3 = s.get('https://www.govdeals.com/sitemap.xml', timeout=10)
    print(f"  [{r3.status_code}] sitemap.xml ({len(r3.text)} chars)")
    if r3.status_code == 200:
        soup3 = BeautifulSoup(r3.text, 'xml')
        urls = soup3.find_all('url')
        print(f"  URLs no sitemap: {len(urls)}")
        asset_urls = [u for u in urls if 'asset' in u.find('loc').get_text().lower()]
        print(f"  URLs de assets: {len(asset_urls)}")
        for u in asset_urls[:5]:
            print(f"    {u.find('loc').get_text()[:80]}")
except Exception as e:
    print(f"  [ERR] {str(e)[:50]}")

# Tentar a antiga URL do GovDeals (ColdFusion)
print("\n--- URL antiga ColdFusion ---")
try:
    r4 = s.get('https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchtext=golf+cart&rowCount=25', timeout=20)
    soup4 = BeautifulSoup(r4.text, 'html.parser')
    print(f"  [{r4.status_code}] ({len(r4.text)} chars)")
    
    # Verificar se há links de assets escondidos
    all_links = soup4.find_all('a', href=True)
    asset_links = [l for l in all_links if 'asset' in l['href'].lower() or 'itemid' in l['href'].lower()]
    print(f"  Links de assets: {len(asset_links)}")
    
    # Verificar se tem dados no HTML (mesmo que SPA)
    # Procurar JSON embutido
    for script in soup4.find_all('script'):
        text = script.string or ''
        if 'asset' in text.lower() or 'item' in text.lower():
            if len(text) > 200:
                print(f"  Script com dados ({len(text)} chars): {text[:200]}")
    
    # Verificar se a página tem noscript com conteúdo
    noscript = soup4.find('noscript')
    if noscript:
        ns_text = noscript.get_text(strip=True)
        print(f"  <noscript>: {ns_text[:200]}")
        
except Exception as e:
    print(f"  [ERR] {str(e)[:50]}")

# Tentar GovDeals com cookie de sessão
print("\n--- GovDeals com sessão ---")
try:
    # Primeiro visitar a homepage para pegar cookies
    s2 = requests.Session()
    s2.headers.update(config.HEADERS)
    r5 = s2.get('https://www.govdeals.com/', timeout=15)
    print(f"  Homepage: [{r5.status_code}] Cookies: {dict(s2.cookies)}")
    
    # Agora tentar a API com cookies
    r6 = s2.get('https://www.govdeals.com/api/search/assets', 
                params={'q': 'golf cart', 'page': '1', 'pageSize': '25'},
                headers={'Accept': 'application/json', 'Referer': 'https://www.govdeals.com/en/search?q=golf+cart'},
                timeout=10)
    print(f"  API com cookies: [{r6.status_code}] {r6.headers.get('content-type', '')[:30]} ({len(r6.text)} chars)")
    if r6.status_code == 200 and 'json' in r6.headers.get('content-type', ''):
        data = r6.json()
        print(f"    SUCESSO! {data}")
except Exception as e:
    print(f"  [ERR] {str(e)[:50]}")

print("\n✅ Teste de extração concluído!")
