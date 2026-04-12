# Agente Inteligente de Leiloes Americanos

Um sistema completo em Python para monitorar sites de leilao americanos, analisar oportunidades com Inteligencia Artificial e gerenciar todo o ciclo de vida do lote (da arrematacao a revenda) via Telegram.

**Versao 2.0 - Otimizada para Render Free (512MB RAM) - Sem Selenium**

## Funcionalidades

### 1. Monitoramento Inteligente
- **Scraping Automatico:** Monitora 5 sites (GovDeals, Public Surplus, BidSpotter, AVGear, JJ Kane)
- **Leve e Rapido:** Usa apenas `requests` + `BeautifulSoup` (sem Selenium/Chrome)
- **Analise com IA:** Usa GPT-4.1-mini para identificar o item, estimar valor de mercado e calcular margem de lucro
- **Alertas no Telegram:** Envia notificacoes apenas para "Otimas" ou "Boas" oportunidades
- **Prevencao de Duplicatas:** Banco de dados SQLite garante que voce nao receba o mesmo alerta duas vezes

### 2. Agenda e Lembretes
- **Agendamento:** Registre leiloes de interesse com data, hora e lance minimo
- **Lembretes Automaticos:** Receba alertas no Telegram 24h, 1h e 15m antes do leilao comecar

### 3. Pos-Arrematacao e Logistica
- **Registro de Lotes:** Registre itens ganhos com valor pago e localizacao
- **Gestao de Frete:** Adicione transportadora e codigo de rastreio
- **Rastreamento:** Acompanhe o status dos itens em transito

### 4. Estoque e Vendas
- **Controle de Estoque:** Mova itens entregues para o estoque com preco sugerido de revenda
- **Registro de Vendas:** Marque itens como vendidos e registre o valor final
- **Dashboard Financeiro:** Acompanhe total investido, total em vendas e lucro acumulado

## Instalacao Local

1. **Clone o repositorio:**
   ```bash
   git clone https://github.com/ronaldo33vilela/agente-leiloes.git
   cd agente-leiloes
   ```

2. **Instale as dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure as variaveis de ambiente:**
   Edite o arquivo `config.py` ou defina as variaveis de ambiente:
   - `TELEGRAM_TOKEN`: Token do seu bot (obtido no @BotFather)
   - `TELEGRAM_CHAT_ID`: Seu ID do Telegram (obtido no @userinfobot)
   - `OPENAI_API_KEY`: Sua chave da API da OpenAI

4. **Configure as palavras-chave:**
   Edite a lista `KEYWORDS` no arquivo `config.py` com os termos que deseja buscar.

5. **Execute o agente:**
   ```bash
   python main.py
   ```

## Comandos do Telegram

Envie `/help` para o seu bot para ver a lista completa de comandos:

**Monitoramento:**
- `/buscar [termo]` - Busca manual nos sites

**Agenda:**
- `/agendar` - Registra um leilao na agenda
- `/agenda` - Lista todos os leiloes agendados
- `/cancelar [ID]` - Remove um leilao da agenda

**Pos-Arrematacao:**
- `/ganhou` - Registra um lote arrematado
- `/frete [ID]` - Registra frete/transportadora
- `/rastrear` - Consulta status de itens em transito
- `/entregue [ID]` - Marca item como entregue

**Estoque e Vendas:**
- `/estoque` - Lista itens disponiveis para venda
- `/vender [ID] [Valor]` - Marca um item como vendido
- `/dashboard` - Resumo completo de investimentos e lucros

## Deploy Gratuito 24/7 no Render.com

### Passo a Passo

1. Crie uma conta no [Render](https://render.com)
2. Conecte seu GitHub e crie um novo **Web Service**
3. Selecione o repositorio com este codigo
4. Configuracoes:
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120`
   - **Instance Type:** Free
5. Adicione as variaveis de ambiente (Environment Variables):
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `OPENAI_API_KEY`
   - `CHECK_INTERVAL` (opcional, padrao: 3600)
6. Clique em **Create Web Service**

### Por que Web Service e nao Background Worker?

O plano gratuito do Render desliga Background Workers apos inatividade. Usando um Web Service com Flask, o servico permanece ativo respondendo health checks, enquanto o monitoramento roda em threads de background.

## Otimizacoes de Memoria (v2.0)

| Mudanca | Antes | Depois |
|---------|-------|--------|
| Scraping | Selenium + Chrome (~300MB) | requests + BeautifulSoup (~20MB) |
| Scrapers | Todos instanciados na RAM | Instanciados sob demanda e destruidos |
| Logging | Arquivo + Console | Apenas Console (economiza disco) |
| Web Server | Nenhum | Flask leve para health check |
| Coleta de lixo | Automatica | Forcada apos cada rodada |

## Limitacoes e Avisos

- **Sites SPA:** Alguns sites (como GovDeals) usam Angular/React e podem retornar menos resultados sem JavaScript. Os scrapers tentam APIs internas e endpoints alternativos para compensar.
- **Bloqueios de IP:** Sites de leilao podem bloquear IPs de servidores em nuvem. Se os scrapers pararem de retornar resultados, considere usar proxies residenciais.
- **Mudancas de Layout:** Se os sites mudarem sua estrutura HTML, os scrapers precisarao ser atualizados.
- **Custos da API:** A analise usa a API da OpenAI, que tem custos associados (embora o modelo gpt-4.1-mini seja muito barato).

## Estrutura do Projeto

```
agente-leiloes/
├── main.py                 # Ponto de entrada (Flask + Agente)
├── config.py               # Configuracoes e variaveis de ambiente
├── requirements.txt        # Dependencias (sem Selenium!)
├── test_scrapers.py        # Script de teste dos scrapers
├── README.md               # Este arquivo
├── modules/
│   ├── __init__.py
│   ├── analyzer.py         # Analise com OpenAI GPT-4.1-mini
│   ├── database.py         # Camada de dados SQLite
│   ├── telegram_bot.py     # Bot do Telegram (comandos)
│   ├── agenda.py           # Gerenciador de agenda/lembretes
│   └── post_auction.py     # Gerenciador de pos-arrematacao
└── scrapers/
    ├── __init__.py
    ├── base_scraper.py     # Classe base (requests + BS4)
    ├── govdeals.py         # Scraper GovDeals
    ├── publicsurplus.py    # Scraper Public Surplus
    ├── bidspotter.py       # Scraper BidSpotter
    ├── avgear.py           # Scraper AVGear (Shopify)
    └── jjkane.py           # Scraper JJ Kane
```
