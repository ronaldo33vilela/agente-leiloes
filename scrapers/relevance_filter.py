"""
Módulo de filtro de relevância para scrapers.
Verifica se um item é realmente relevante para o termo buscado.
"""
import re
from typing import List, Tuple

def extract_keywords(search_term: str) -> List[str]:
    """Extrai palavras-chave do termo de busca."""
    # Remove palavras muito curtas e stop words
    stop_words = {"de", "do", "da", "e", "ou", "a", "o", "em", "para", "por", "com", "sem"}
    keywords = []
    for word in search_term.lower().split():
        word = re.sub(r'[^a-z0-9]', '', word)
        if len(word) > 2 and word not in stop_words:
            keywords.append(word)
    return keywords if keywords else [search_term.lower()]

def calculate_relevance_score(title: str, search_term: str) -> float:
    """
    Calcula score de relevância (0.0 a 1.0) para um item.
    
    Score 1.0: Título contém o termo exato
    Score 0.8+: Título contém todas as palavras-chave
    Score 0.5+: Título contém a maioria das palavras-chave
    Score < 0.5: Não relevante
    """
    if not title or not search_term:
        return 0.0
    
    title_lower = title.lower()
    search_lower = search_term.lower()
    
    # Termo exato no título
    if search_lower in title_lower:
        return 1.0
    
    # Extrair palavras-chave
    keywords = extract_keywords(search_term)
    if not keywords:
        return 0.0
    
    # Contar quantas palavras-chave aparecem no título
    matches = 0
    for keyword in keywords:
        if keyword in title_lower:
            matches += 1
    
    if matches == 0:
        return 0.0
    
    # Score proporcional
    score = matches / len(keywords)
    
    # Penalidade por palavras negativas comuns
    negative_words = [
        "lot of", "assorted", "mixed", "various", "collection",
        "bundle", "box of", "pallet", "liquidation"
    ]
    for neg in negative_words:
        if neg in title_lower and search_lower not in title_lower:
            score *= 0.7  # Reduz score se for lote genérico
    
    return min(score, 1.0)

def is_relevant(title: str, search_term: str, min_score: float = 0.5) -> bool:
    """
    Verifica se um item é relevante para o termo buscado.
    
    Args:
        title: Título do item
        search_term: Termo buscado
        min_score: Score mínimo para considerar relevante (0.0-1.0)
    
    Returns:
        True se relevante, False caso contrário
    """
    score = calculate_relevance_score(title, search_term)
    return score >= min_score

def filter_items(items: List[dict], search_term: str, min_score: float = 0.5) -> List[dict]:
    """
    Filtra lista de itens mantendo apenas os relevantes.
    
    Args:
        items: Lista de dicts com chave 'title'
        search_term: Termo buscado
        min_score: Score mínimo para considerar relevante
    
    Returns:
        Lista filtrada com apenas itens relevantes
    """
    filtered = []
    for item in items:
        title = item.get("title", "")
        if is_relevant(title, search_term, min_score):
            score = calculate_relevance_score(title, search_term)
            item["_relevance_score"] = score
            filtered.append(item)
    
    # Ordenar por relevância (maior score primeiro)
    filtered.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
    return filtered
