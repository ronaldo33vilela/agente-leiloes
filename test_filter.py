"""
Teste do filtro de relevância com diferentes cenários.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['TELEGRAM_TOKEN'] = '123456:ABC'
os.environ['TELEGRAM_CHAT_ID'] = '123456'
os.environ['OPENAI_API_KEY'] = 'test'

from scrapers.relevance_filter import calculate_relevance_score, filter_items, is_relevant

print("=" * 60)
print("  TESTE DO FILTRO DE RELEVÂNCIA")
print("=" * 60)

# Teste 1: Termos exatos
print("\n--- Teste 1: Termos exatos ---")
test_cases = [
    ("golf cart", "Clubcar Golf cart", "Deveria ser 1.0"),
    ("golf cart", "New Unused 2025 Golf Cart", "Deveria ser 1.0"),
    ("golf cart", "CLUB CAR Transporter 6-seater golf cart charger included", "Deveria ser 1.0"),
    ("golf cart", "2008 Club Car electric golf cart", "Deveria ser 1.0"),
    ("golf cart", "LOT 17 - UTILITY CART", "Parcial - só 'cart'"),
    ("golf cart", "LOT 7 - E-Z-GO CART", "Parcial - só 'cart'"),
    ("golf cart", "KQI3 Pro Scooter", "Irrelevante"),
    ("golf cart", "Auction#206- Country server", "Irrelevante"),
    ("golf cart", "New Holland 5450 Tractor", "Irrelevante"),
]

for search_term, title, expected in test_cases:
    score = calculate_relevance_score(title, search_term)
    relevant = is_relevant(title, search_term, min_score=0.5)
    emoji = "✅" if relevant else "❌"
    print(f"  {emoji} Score: {score:.2f} | '{title[:50]}' | {expected}")

# Teste 2: Termos de áudio
print("\n--- Teste 2: Termos de áudio ---")
audio_cases = [
    ("Allen Heath SQ5", "Allen & Heath SQ5 Digital Mixer", "Deveria ser alta"),
    ("Allen Heath SQ5", "Allen Heath SQ-5 48-Channel Mixer", "Deveria ser alta"),
    ("Allen Heath SQ5", "Random Audio Equipment Lot", "Irrelevante"),
    ("Allen Heath", "Allen & Heath dLive S5000", "Parcial"),
    ("QSC K12", "QSC K12.2 Powered Speaker", "Alta"),
    ("QSC K12", "QSC KW122 Speaker", "Parcial"),
    ("QSC K12", "Yamaha DXR12 Speaker", "Irrelevante"),
]

for search_term, title, expected in audio_cases:
    score = calculate_relevance_score(title, search_term)
    relevant = is_relevant(title, search_term, min_score=0.5)
    emoji = "✅" if relevant else "❌"
    print(f"  {emoji} Score: {score:.2f} | '{search_term}' → '{title[:50]}' | {expected}")

# Teste 3: Filtro com lista de itens
print("\n--- Teste 3: Filtro com lista de itens ---")
items = [
    {"title": "Clubcar Golf cart", "link": "http://example.com/1"},
    {"title": "New Unused 2025 Golf Cart", "link": "http://example.com/2"},
    {"title": "KQI3 Pro Scooter", "link": "http://example.com/3"},
    {"title": "Auction#206- Country server", "link": "http://example.com/4"},
    {"title": "LOT 17 - UTILITY CART", "link": "http://example.com/5"},
    {"title": "LOT 7 - E-Z-GO CART", "link": "http://example.com/6"},
    {"title": "New Holland 5450 Tractor", "link": "http://example.com/7"},
    {"title": "CLUB CAR Transporter 6-seater golf cart", "link": "http://example.com/8"},
    {"title": "Lot of assorted items mixed", "link": "http://example.com/9"},
    {"title": "2008 Club Car electric golf cart", "link": "http://example.com/10"},
]

print(f"  Itens antes do filtro: {len(items)}")
filtered = filter_items(items, "golf cart", min_score=0.5)
print(f"  Itens depois do filtro (score >= 0.5): {len(filtered)}")
for item in filtered:
    print(f"    → Score: {item.get('_relevance_score', 0):.2f} | {item['title'][:50]}")

# Teste com score mais baixo
filtered_low = filter_items(items.copy(), "golf cart", min_score=0.3)
print(f"\n  Itens com score >= 0.3: {len(filtered_low)}")
for item in filtered_low:
    print(f"    → Score: {item.get('_relevance_score', 0):.2f} | {item['title'][:50]}")

# Teste 4: Verificar se o filtro não está muito restritivo
print("\n--- Teste 4: Verificar sensibilidade ---")
tricky_cases = [
    ("golf cart", "Golf Cart - EZ-GO TXT 48V Electric", 1.0),
    ("golf cart", "EZGO Golf Cart Charger 36V", 1.0),
    ("golf cart", "Cart for golf equipment", 1.0),
    ("golf cart", "Go Kart Racing", 0.5),  # "cart" parcial
    ("allen heath", "Allen & Heath SQ5", 0.5),  # & vs space
    ("allen heath", "Allen-Heath Mixer", 0.5),  # - vs space
]

for search_term, title, expected_min in tricky_cases:
    score = calculate_relevance_score(title, search_term)
    ok = score >= expected_min
    emoji = "✅" if ok else "❌"
    print(f"  {emoji} Score: {score:.2f} (esperado >= {expected_min}) | '{search_term}' → '{title[:50]}'")

print("\n✅ Teste do filtro concluído!")
