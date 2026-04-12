import os
import sys
import json
import logging
from openai import OpenAI

# Adiciona o diretório pai ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger('Analyzer')

class AuctionAnalyzer:
    """Módulo para analisar itens de leilão usando LLM."""
    
    def __init__(self):
        self.api_key = config.OPENAI_API_KEY
        if not self.api_key:
            logger.warning("OPENAI_API_KEY não configurada. A análise LLM não funcionará.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
            
    def analyze_item(self, title, price, site, keyword):
        """
        Analisa um item usando GPT-4.1-mini para estimar valor e margem de lucro.
        Retorna um dicionário com a análise.
        """
        if not self.client:
            return self._fallback_analysis(title, price)
            
        prompt = f"""
        Você é um especialista em avaliação de equipamentos de leilão americano.
        Analise o seguinte item encontrado em um leilão:
        
        Título/Descrição: {title}
        Preço Atual: {price}
        Site: {site}
        Categoria de Busca: {keyword}
        
        Sua tarefa é:
        1. Identificar exatamente o que é o item
        2. Estimar o valor de mercado atual (mercado de usados/revenda nos EUA)
        3. Calcular a margem de lucro estimada (considerando o preço atual)
        4. Dar uma recomendação final: ÓTIMA OPORTUNIDADE, BOA OPORTUNIDADE, REGULAR ou NÃO RECOMENDADO
        
        Responda APENAS com um JSON válido no seguinte formato:
        {{
            "item_type": "Descrição curta do tipo de item",
            "estimated_value": "Valor estimado em USD (ex: $500 - $700)",
            "profit_margin": "Margem estimada em % ou USD",
            "recommendation": "ÓTIMA OPORTUNIDADE|BOA OPORTUNIDADE|REGULAR|NÃO RECOMENDADO",
            "reasoning": "Breve justificativa (1-2 frases)"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Você é um avaliador especialista e responde apenas em JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Erro na análise LLM: {e}")
            return self._fallback_analysis(title, price)
            
    def _fallback_analysis(self, title, price):
        """Análise de fallback caso a API falhe."""
        return {
            "item_type": "Não foi possível identificar (Erro na API)",
            "estimated_value": "Desconhecido",
            "profit_margin": "Desconhecida",
            "recommendation": "REGULAR",
            "reasoning": "Análise automática indisponível no momento."
        }
