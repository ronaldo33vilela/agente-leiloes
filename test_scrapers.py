"""
Script de teste para validar os scrapers individualmente.
Testa cada scraper com uma palavra-chave e exibe os resultados.
"""
import sys
import os
import json

# Garante que o diretório do projeto está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.govdeals import GovDealsScraper
from scrapers.publicsurplus import PublicSurplusScraper
from scrapers.bidspotter import BidSpotterScraper
from scrapers.avgear import AVGearScraper
from scrapers.jjkane import JJKaneScraper
from modules import database

# Inicializa o banco de dados
database.init_db()

def test_scraper(scraper_class, keyword):
    """Testa um scraper individual."""
    scraper = scraper_class()
    print(f"\n{'='*60}")
    print(f"Testando: {scraper.site_name}")
    print(f"Palavra-chave: {keyword}")
    print(f"{'='*60}")
    
    try:
        results = scraper.search(keyword)
        print(f"Resultados encontrados: {len(results)}")
        
        for i, item in enumerate(results[:3]):  # Mostra apenas os 3 primeiros
            print(f"\n  [{i+1}] {item['title'][:80]}")
            print(f"      Preço: {item['price']}")
            print(f"      Link: {item['link'][:80]}...")
            
        return results
        
    except Exception as e:
        print(f"ERRO: {e}")
        return []

if __name__ == "__main__":
    keyword = "golf cart"
    
    all_results = []
    
    # Testa cada scraper
    scrapers = [
        GovDealsScraper,
        PublicSurplusScraper,
        BidSpotterScraper,
        AVGearScraper,
        JJKaneScraper
    ]
    
    for scraper_class in scrapers:
        results = test_scraper(scraper_class, keyword)
        all_results.extend(results)
    
    print(f"\n{'='*60}")
    print(f"TOTAL DE RESULTADOS: {len(all_results)}")
    print(f"{'='*60}")
    
    # Testa o banco de dados
    print("\nTestando banco de dados...")
    database.init_db()
    print("Banco de dados inicializado com sucesso!")
    
    # Salva resultados em JSON para referência
    with open(os.path.join(os.path.dirname(__file__), "test_results.json"), 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"Resultados salvos em test_results.json")
