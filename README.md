# 🤖 Agente Inteligente de Leilões Americanos

Um sistema completo em Python para monitorar sites de leilão americanos, analisar oportunidades com Inteligência Artificial e gerenciar todo o ciclo de vida do lote (da arrematação à revenda) via Telegram.

## 🌟 Funcionalidades

### 1. Monitoramento Inteligente
- **Scraping Automático:** Monitora 5 sites (GovDeals, Public Surplus, BidSpotter, AVGear, JJ Kane)
- **Análise com IA:** Usa GPT-4.1-mini para identificar o item, estimar valor de mercado e calcular margem de lucro
- **Alertas no Telegram:** Envia notificações apenas para "Ótimas" ou "Boas" oportunidades
- **Prevenção de Duplicatas:** Banco de dados SQLite garante que você não receba o mesmo alerta duas vezes

### 2. Agenda e Lembretes
- **Agendamento:** Registre leilões de interesse com data, hora e lance mínimo
- **Lembretes Automáticos:** Receba alertas no Telegram 24h, 1h e 15m antes do leilão começar

### 3. Pós-Arrematação e Logística
- **Registro de Lotes:** Registre itens ganhos com valor pago e localização
- **Gestão de Frete:** Adicione transportadora e código de rastreio
- **Rastreamento:** Acompanhe o status dos itens em trânsito

### 4. Estoque e Vendas
- **Controle de Estoque:** Mova itens entregues para o estoque com preço sugerido de revenda
- **Registro de Vendas:** Marque itens como vendidos e registre o valor final
- **Dashboard Financeiro:** Acompanhe total investido, total em vendas e lucro acumulado

## 🛠️ Instalação Local

1. **Clone o repositório ou baixe os arquivos**

2. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```
   *Nota: O sistema usa Selenium para sites que carregam conteúdo via JavaScript. Certifique-se de ter o Google Chrome instalado no seu sistema.*

3. **Configure as variáveis de ambiente:**
   Edite o arquivo `config.py` ou defina as variáveis de ambiente:
   - `TELEGRAM_TOKEN`: Token do seu bot (obtido no @BotFather)
   - `TELEGRAM_CHAT_ID`: Seu ID do Telegram (obtido no @userinfobot)
   - `OPENAI_API_KEY`: Sua chave da API da OpenAI

4. **Configure as palavras-chave:**
   Edite a lista `KEYWORDS` no arquivo `config.py` com os termos que deseja buscar.

5. **Execute o agente:**
   ```bash
   python main.py
   ```

## 📱 Comandos do Telegram

Envie `/help` para o seu bot para ver a lista completa de comandos:

**Monitoramento:**
- `/agendar` - Registra um leilão na agenda
- `/agenda` - Lista todos os leilões agendados
- `/cancelar [ID]` - Remove um leilão da agenda

**Pós-Arrematação:**
- `/ganhou` - Registra um lote arrematado
- `/frete [ID]` - Registra frete/transportadora
- `/rastrear` - Consulta status de itens em trânsito
- `/entregue [ID]` - Marca item como entregue e move para estoque

**Estoque e Vendas:**
- `/estoque` - Lista itens disponíveis para venda
- `/vender [ID] [Valor]` - Marca um item como vendido
- `/dashboard` - Resumo completo de investimentos e lucros

## 🚀 Deploy Gratuito 24/7 (Render / Railway)

Para manter o bot rodando 24 horas por dia sem precisar deixar seu computador ligado:

### Opção 1: Render.com (Recomendado)
1. Crie uma conta no [Render](https://render.com)
2. Conecte seu GitHub e crie um novo "Background Worker"
3. Selecione o repositório com este código
4. Configurações:
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt && apt-get update && apt-get install -y wget gnupg && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && apt-get update && apt-get install -y google-chrome-stable`
   - **Start Command:** `python main.py`
5. Adicione as variáveis de ambiente (Environment Variables):
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `OPENAI_API_KEY`
6. Clique em "Create Background Worker"

### Opção 2: Railway.app
1. Crie uma conta no [Railway](https://railway.app)
2. Clique em "New Project" > "Deploy from GitHub repo"
3. Adicione as variáveis de ambiente na aba "Variables"
4. O Railway detectará automaticamente o `requirements.txt` e fará o deploy.
   *Nota: Para o Selenium funcionar no Railway, você precisará adicionar um `nixpacks.toml` ou `Dockerfile` configurando o Chrome.*

## ⚠️ Limitações e Avisos
- **Bloqueios de IP:** Sites de leilão podem bloquear IPs de servidores em nuvem. Se os scrapers pararem de retornar resultados, considere usar proxies residenciais.
- **Mudanças de Layout:** Se os sites mudarem sua estrutura HTML, os scrapers precisarão ser atualizados.
- **Custos da API:** A análise usa a API da OpenAI, que tem custos associados (embora o modelo gpt-4.1-mini seja muito barato).
