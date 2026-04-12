"""
Investigação parte 3:
- BidSpotter: /en-us/search-results?searchTerm=golf+cart (encontrado no form!)
- GovDeals: corrigir URL do JS bundle
- JJ Kane: /categories/trailers funciona, investigar mais
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
# 1. BIDSPOTTER - /en-us/search-results?searchTerm=
# ============================================================
print("=" * 60)
print("1. BIDSPOTTER - search-results (do formulário!)")
print("=" * 60)

r = s.get('https://www.bidspotter.com/en-us/search-results?searchTerm=golf+cart', timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')
print(f"  [{r.status_code}] search-results?searchTerm=golf+cart")
print(f"  URL final: {r.url[:80]}")
print(f"  Tamanho: {len(r.text)} chars")
title = soup.find('title')
print(f"  Título: {title.get_text()[:60] if title else 'N/A'}")

# Verificar se tem resultados
if 'error' not in r.url.lower():
    # Procurar links de lotes
    lot_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        txt = link.get_text(strip=True)
        if any(k in href.lower() for k in ['lot-details', '/lot/', 'auction-catalogue']):
            if txt and len(txt) > 3:
                lot_links.append((txt, href))
    
    print(f"  Lot links encontrados: {len(lot_links)}")
    for txt, href in lot_links[:10]:
        print(f"    → {txt[:50]} | {href[:70]}")
    
    # Procurar divs de resultado
    result_divs = soup.find_all('div', class_=lambda c: c and any(k in str(c).lower() for k in ['lot', 'result', 'search', 'item', 'card']))
    print(f"  Result divs: {len(result_divs)}")
    
    # Verificar se é SPA
    scripts = soup.find_all('script')
    for script in scripts:
        text = script.string or ''
        if 'searchResults' in text or 'lotData' in text or 'results' in text[:100]:
            print(f"  JS com dados: {text[:200]}")
    
    # Salvar HTML para análise
    with open('/home/ubuntu/agente-leiloes/debug_bidspotter_search.html', 'w') as f:
        f.write(r.text)
    print("  HTML salvo em debug_bidspotter_search.html")

# ============================================================
# 2. GOVDEALS - Corrigir URL do JS bundle
# ============================================================
print("\n" + "=" * 60)
print("2. GOVDEALS - JS bundle corrigido")
print("=" * 60)

r2 = s.get('https://www.govdeals.com/en/search?q=golf+cart', timeout=20)
soup2 = BeautifulSoup(r2.text, 'html.parser')

for script in soup2.find_all('script', src=True):
    src = script['src']
    # Corrigir URL relativa
    if src.startswith('/'):
        full_url = f"https://www.govdeals.com{src}"
    elif src.startswith('http'):
        full_url = src
    else:
        full_url = f"https://www.govdeals.com/{src}"
    
    if 'main' in src:
        print(f"  Baixando: {full_url[:80]}")
        try:
            r3 = s.get(full_url, timeout=15)
            js = r3.text
            print(f"  Tamanho: {len(js)} chars")
            
            # Procurar API endpoints
            apis = re.findall(r'["\'](/api/[^"\']+)["\']', js)
            for api in set(apis):
                print(f"    API: {api}")
            
            # Procurar Algolia
            if 'algolia' in js.lower():
                print("  → ALGOLIA encontrado!")
                app_ids = re.findall(r'["\']([A-Z0-9]{8,12})["\']', js)
                api_keys = re.findall(r'["\']([a-f0-9]{20,40})["\']', js)
                indices = re.findall(r'indexName["\s:=]+["\']([^"\']+)["\']', js)
                print(f"    Possíveis App IDs: {app_ids[:3]}")
                print(f"    Possíveis API Keys: {[k[:15]+'...' for k in api_keys[:3]]}")
                print(f"    Indices: {indices[:3]}")
            
            # Procurar qualquer URL de API
            urls = re.findall(r'https?://[^"\'\\s]+(?:api|search|graphql)[^"\'\\s]*', js, re.IGNORECASE)
            for u in set(urls):
                if len(u) < 200:
                    print(f"    URL: {u[:100]}")
                    
        except Exception as e:
            print(f"  [ERR] {e}")

# ============================================================
# 3. JJ KANE - Investigar categorias que funcionam
# ============================================================
print("\n" + "=" * 60)
print("3. JJ KANE - Categorias e leilões ativos")
print("=" * 60)

# Verificar /categories/trailers que retornou 200
r4 = s.get('https://www.jjkane.com/categories/trailers', timeout=15)
soup4 = BeautifulSoup(r4.text, 'html.parser')
print(f"  [{r4.status_code}] /categories/trailers ({len(r4.text)} chars)")

# Procurar links de itens
for link in soup4.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if '/categories/' in href and href != '/categories/trailers' and txt and len(txt) > 3:
        print(f"  Category: {txt[:40]} | {href[:60]}")

# Listar todas as categorias disponíveis
r5 = s.get('https://www.jjkane.com/', timeout=15)
soup5 = BeautifulSoup(r5.text, 'html.parser')
cat_links = set()
for link in soup5.find_all('a', href=True):
    href = link['href']
    if '/categories/' in href:
        cat_links.add(href)

print(f"\n  Categorias encontradas: {len(cat_links)}")
for cat in sorted(cat_links):
    print(f"    {cat}")

# Verificar um leilão ativo para ver se tem inventário
print("\n  Verificando leilão ativo com inventário...")
r6 = s.get('https://www.jjkane.com/auctions/', timeout=15)
soup6 = BeautifulSoup(r6.text, 'html.parser')

# Procurar datas de leilão
text = soup6.get_text()
date_matches = re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}', text)
for d in date_matches[:5]:
    print(f"  Data de leilão: {d}")

# Procurar links de proxlot ou similar
proxlot_links = [l for l in soup6.find_all('a', href=True) if 'proxibid' in l['href'].lower() or 'proxlot' in l['href'].lower() or 'bidding' in l['href'].lower()]
print(f"  Links de bidding: {len(proxlot_links)}")
for l in proxlot_links[:5]:
    print(f"    → {l.get_text(strip=True)[:40]} | {l['href'][:60]}")

# Verificar se JJ Kane usa Proxibid
for link in soup6.find_all('a', href=True):
    href = link['href']
    if 'proxibid' in href.lower() or 'bidding' in href.lower():
        print(f"  Bidding link: {href[:80]}")

print("\n✅ Investigação parte 3 concluída!")
