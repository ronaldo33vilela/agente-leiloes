# Agente Inteligente de Leiloes Americanos

Um sistema completo em Python para monitorar sites de leilao americanos, analisar oportunidades com Inteligencia Artificial e gerenciar todo o ciclo de vida do lote (da arrematacao a revenda) via Telegram.

**Versao 4.0 - Dashboard Web + Agenda + Historico de Precos + Filtro de Relevancia - Render Free (512MB RAM)**

## Funcionalidades

### 1. Monitoramento Inteligente com Categorias
- **278 Termos de Busca:** Organizados em 23 categorias (Allen & Heath, Shure Axient, Mesas de Luz, Paineis LED, Golf Carts, etc.)
- **Sistema de Prioridade:** Grupo A (prioridade maxima), Grupo B (otima oportunidade), Grupo C (garimpo)
- **Rotacao Automatica:** A cada ciclo (1 hora), processa 25 termos e rotaciona para os proximos
- **Scraping Automatico:** Monitora 5 sites (GovDeals, Public Surplus, BidSpotter, AVGear, JJ Kane)
- **Leve e Rapido:** Usa apenas `requests` + `BeautifulSoup` (sem Selenium/Chrome)
- **Analise com IA:** Usa GPT-4.1-mini para identificar o item, estimar valor de mercado e calcular margem de lucro
- **Alertas no Telegram:** Envia notificacoes apenas para "Otimas" ou "Boas" oportunidades
- **Filtro de Preco:** Preco maximo configuravel por categoria
- **Prevencao de Duplicatas:** Banco de dados SQLite garante que voce nao receba o mesmo alerta duas vezes

### 2. Categorias de Busca

| Prioridade | Categoria | Descricao |
|------------|-----------|-----------|
| A | allen_heath_mixers | Mesas SQ, Qu, GLD, dLive, Avantis, M1, M500 |
| A | shure_axient | Linha Axient Digital completa (AD4D, AD4Q, AXT, ADX) |
| A | lighting_consoles | grandMA2/3, Avolites, Chamsys, ETC, Hog |
| A | led_controllers | Novastar, Colorlight, processadores LED |
| A | combo_* | Combinacoes prontas de alto valor |
| B | *_accessories | Acessorios, stageboxes, Dante cards, cases |
| B | led_panels | Paineis P1.9 a P4.8, indoor/outdoor |
| B | *_smart | Buscas inteligentes por lotes e oportunidades |
| C | allen_heath_smart | Anuncios mal escritos, untested, as-is |
| C | opportunity_terms | Termos genericos: surplus, church audio, salvage |

### 3. Agenda e Lembretes
- **Agendamento:** Registre leiloes de interesse com data, hora e lance minimo
- **Lembretes Automaticos:** Receba alertas no Telegram 24h, 1h e 15m antes do leilao comecar

### 4. Pos-Arrematacao e Logistica
- **Registro de Lotes:** Registre itens ganhos com valor pago e localizacao
- **Gestao de Frete:** Adicione transportadora e codigo de rastreio
- **Rastreamento:** Acompanhe o status dos itens em transito

### 5. Estoque e Vendas
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

4. **Personalize os termos de busca (opcional):**
   Edite o dicionario `SEARCH_TERMS` no arquivo `config.py` para adicionar ou remover termos.
   Ajuste `MAX_PRICE` para definir limites de preco por categoria.

5. **Execute o agente:**
   ```bash
   python main.py
   ```

## Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `TELEGRAM_TOKEN` | - | Token do bot Telegram |
| `TELEGRAM_CHAT_ID` | - | Chat ID do Telegram |
| `OPENAI_API_KEY` | - | Chave da API OpenAI |
| `CHECK_INTERVAL` | 3600 | Intervalo entre ciclos (segundos) |
| `TERMS_PER_CYCLE` | 25 | Termos processados por ciclo |
| `REQUEST_DELAY` | 3 | Delay entre requisicoes (segundos) |
| `MIN_PROFIT_MARGIN` | 30 | Margem minima de lucro (%) |

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

## Endpoints da API

| Rota | Descricao |
|------|-----------|
| `GET /` | Health check com info do sistema |
| `GET /health` | Health check simples |
| `GET /stats` | Estatisticas do agente |
| `GET /categories` | Lista categorias, prioridades e limites de preco |
| `GET /dashboard` | Dashboard web completo (dark theme) |
| `POST /webhook` | Webhook do Telegram |
| `GET /api/category/<name>` | Termos e itens de uma categoria |
| `GET /api/watchlist` | Itens da agenda/watchlist |
| `GET /api/price-history` | Historico de precos |
| `POST /api/clear-data` | Limpa todos os dados do banco |
| `POST /api/scan-now` | Dispara varredura manual |

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
   - `TERMS_PER_CYCLE` (opcional, padrao: 25)
   - `REQUEST_DELAY` (opcional, padrao: 3)
   - `MIN_PROFIT_MARGIN` (opcional, padrao: 30)
6. Clique em **Create Web Service**

### Por que Web Service e nao Background Worker?

O plano gratuito do Render desliga Background Workers apos inatividade. Usando um Web Service com Flask, o servico permanece ativo respondendo health checks, enquanto o monitoramento roda em threads de background.

## Otimizacoes de Memoria (v3.0)

| Mudanca | Antes | Depois |
|---------|-------|--------|
| Scraping | Selenium + Chrome (~300MB) | requests + BeautifulSoup (~20MB) |
| Scrapers | Todos instanciados na RAM | Instanciados sob demanda e destruidos |
| Busca | Todas as keywords por ciclo | Rotacao de 25 termos/ciclo |
| Prioridade | Sem prioridade | Grupo A > B > C |
| Filtros | Sem filtro de preco | Preco maximo por categoria |
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
├── main.py                 # Ponto de entrada (Flask + Agente + Rotacao)
├── config.py               # Configuracoes, categorias e prioridades
├── requirements.txt        # Dependencias (sem Selenium!)
├── test_scrapers.py        # Script de teste dos scrapers
├── README.md               # Este arquivo
├── database/
│   ├── auctions.db         # Banco SQLite (criado automaticamente)
│   └── rotation_state.json # Estado da rotacao (criado automaticamente)
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
    ├── avgear.py           # Scraper AVGear (leiloes via Joseph Finn)
    ├── jjkane.py           # Scraper JJ Kane
    ├── relevance_filter.py # Filtro de relevancia por keywords
    └── auction_utils.py    # Utilitarios para filtrar leiloes ativos
```
