"""
Teste completo dos scrapers reescritos.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['TELEGRAM_TOKEN'] = '123456:ABC'
os.environ['TELEGRAM_CHAT_ID'] = '123456'
os.environ['OPENAI_API_KEY'] = 'test'

KEYWORD = "golf cart"
results_log = {}

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ============================================================
# 1. BidSpotter (reescrito)
# ============================================================
section("1. BIDSPOTTER (reescrito)")
try:
    from scrapers.bidspotter import BidSpotterScraper
    scraper = BidSpotterScraper()
    items = scraper.search(KEYWORD)
    print(f"  Resultado: {len(items)} itens")
    for item in items[:5]:
        print(f"    → {item.get('title', 'N/A')[:50]} | {item.get('price', 'N/A')} | {item.get('link', '')[:60]}")
    results_log['bidspotter'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO: {e}")
    import traceback; traceback.print_exc()
    results_log['bidspotter'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# 2. Public Surplus (sem mudanças)
# ============================================================
section("2. PUBLIC SURPLUS")
try:
    from scrapers.publicsurplus import PublicSurplusScraper
    scraper = PublicSurplusScraper()
    items = scraper.search(KEYWORD)
    print(f"  Resultado: {len(items)} itens")
    for item in items[:5]:
        print(f"    → {item.get('title', 'N/A')[:50]} | {item.get('price', 'N/A')} | {item.get('link', '')[:60]}")
    results_log['publicsurplus'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO: {e}")
    import traceback; traceback.print_exc()
    results_log['publicsurplus'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# 3. GovDeals (reescrito)
# ============================================================
section("3. GOVDEALS (reescrito)")
try:
    from scrapers.govdeals import GovDealsScraper
    scraper = GovDealsScraper()
    items = scraper.search(KEYWORD)
    print(f"  Resultado: {len(items)} itens")
    for item in items[:5]:
        print(f"    → {item.get('title', 'N/A')[:50]} | {item.get('price', 'N/A')} | {item.get('link', '')[:60]}")
    results_log['govdeals'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO: {e}")
    import traceback; traceback.print_exc()
    results_log['govdeals'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# 4. JJ Kane (reescrito)
# ============================================================
section("4. JJ KANE (reescrito)")
try:
    from scrapers.jjkane import JJKaneScraper
    scraper = JJKaneScraper()
    items = scraper.search(KEYWORD)
    print(f"  Resultado: {len(items)} itens")
    for item in items[:5]:
        print(f"    → {item.get('title', 'N/A')[:50]} | {item.get('price', 'N/A')} | {item.get('link', '')[:60]}")
    results_log['jjkane'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO: {e}")
    import traceback; traceback.print_exc()
    results_log['jjkane'] = f"ERRO: {e}"

time.sleep(2)

# ============================================================
# 5. AVGear (sem mudanças)
# ============================================================
section("5. AVGEAR")
try:
    from scrapers.avgear import AVGearScraper
    scraper = AVGearScraper()
    items = scraper.search(KEYWORD)
    print(f"  Resultado: {len(items)} itens")
    for item in items[:5]:
        print(f"    → {item.get('title', 'N/A')[:50]} | {item.get('price', 'N/A')} | {item.get('link', '')[:60]}")
    results_log['avgear'] = len(items)
except Exception as e:
    print(f"  ❌ ERRO: {e}")
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
        emoji = "✅" if count > 0 else "⚠️"
        print(f"  {emoji} {platform}: {count} itens")
        total += count
    else:
        print(f"  ❌ {platform}: {count}")
print(f"\nTotal: {total} itens")

# Salvar
with open('/home/ubuntu/agente-leiloes/test_rewrite_results.json', 'w') as f:
    json.dump(results_log, f, indent=2)
