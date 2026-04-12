"""\nScript de teste para validar os scrapers individualmente.\nTesta cada scraper com termos de busca por categoria (config.SEARCH_TERMS).\nTodos os scrapers usam apenas requests + BeautifulSoup (sem Selenium).\n"""
import sys
import os
import json
import gc

# Garante que o diretório do projeto está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from scrapers.govdeals import GovDealsScraper
from scrapers.publicsurplus import PublicSurplusScraper
from scrapers.bidspotter import BidSpotterScraper
from scrapers.avgear import AVGearScraper
from scrapers.jjkane import JJKaneScraper
from modules import database

# Inicializa o banco de dados
database.init_db()

def test_scraper(scraper_class, keyword, category="test"):
    """Testa um scraper individual."""
    scraper = scraper_class()
    print(f"\n{'='*60}")
    print(f"Testando: {scraper.site_name}")
    print(f"Categoria: {category}")
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
    finally:
        # Libera memória
        scraper.session.close()
        del scraper
        gc.collect()

if __name__ == "__main__":
    all_results = []
    
    # Scrapers disponíveis
    scrapers = [
        GovDealsScraper,
        PublicSurplusScraper,
        BidSpotterScraper,
        AVGearScraper,
        JJKaneScraper
    ]
    
    # Seleciona 1 termo de cada categoria de prioridade A para teste rápido
    test_terms = []
    for cat in config.PRIORITY_A:
        terms = config.SEARCH_TERMS.get(cat, [])
        if terms:
            test_terms.append((cat, terms[0]))
    
    print(f"Testando {len(test_terms)} categorias de prioridade A...")
    print(f"(limitando a 3 categorias para teste rápido)\n")
    
    for category, keyword in test_terms[:3]:
        for scraper_class in scrapers:
            results = test_scraper(scraper_class, keyword, category)
            all_results.extend(results)
    
    print(f"\n{'='*60}")
    print(f"TOTAL DE RESULTADOS: {len(all_results)}")
    print(f"{'='*60}")
    
    # Testa o banco de dados
    print("\nTestando banco de dados...")
    database.init_db()
    print("Banco de dados inicializado com sucesso!")
    
    # Resumo de categorias configuradas
    print(f"\nResumo de categorias configuradas:")
    for cat, terms in config.SEARCH_TERMS.items():
        priority = "A" if cat in config.PRIORITY_A else "B" if cat in config.PRIORITY_B else "C"
        print(f"  [{priority}] {cat}: {len(terms)} termos")
    print(f"\nTotal de termos: {sum(len(v) for v in config.SEARCH_TERMS.values())}")
    
    # Salva resultados em JSON para referência
    with open(os.path.join(os.path.dirname(__file__), "test_results.json"), 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Resultados salvos em test_results.json")
