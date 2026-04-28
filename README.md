# LinkedIn Posting Agent

Agente autônomo que pesquisa, redige e publica posts no LinkedIn diariamente — com aprovação humana obrigatória antes de qualquer publicação.

## Como funciona

```
06:00 BRT   →   Pesquisa artigos recentes (Tavily)
            →   Redige post em inglês (Claude)
            →   Revisa copyright e segurança
            →   Envia rascunho por e-mail com link de aprovação

          ┌──────────────────────────────┐
          │  Você abre o link no e-mail  │
          │  Preview do post estilo LI   │
          │  [Aprovar]  [Pedir Reescrita]│
          └──────────────────────────────┘

09:00 BRT   →   Publica no LinkedIn (se aprovado)
            →   Envia confirmação por e-mail
```

**Tópicos alternados:** IA → Mercado Financeiro Internacional → IA → …

**Formatos rotativos por dia:**
| Dia | Formato |
|---|---|
| Segunda | Análise / Opinião |
| Terça | Lista ("5 things about X") |
| Quarta | Notícia com contexto |
| Quinta | Tendência / Previsão |
| Sexta | Resumo da semana |

---

## Pré-requisitos

- Python 3.12+
- Conta na [API da Anthropic](https://console.anthropic.com) (Claude)
- Conta na [Tavily](https://tavily.com) (free tier: 1.000 buscas/mês)
- App criado no [LinkedIn Developers](https://www.linkedin.com/developers/apps)
- Conta Gmail com verificação em 2 etapas ativa
- Conta no [Railway](https://railway.app) (deploy gratuito)

---

## Instalação local

```bash
# 1. Clone o repositório
git clone <url-do-repo>
cd Agente-Linkedin-pessoal

# 2. Crie o ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure os arquivos
cp config.yaml.example config.yaml
cp .env.example .env
```

---

## Configuração

### 1. `config.yaml` — comportamento do agente

Edite o arquivo `config.yaml` com seus dados. Os principais campos:

```yaml
profile:
  name: "Seu Nome"
  role: "Sua função/cargo"
  language: "en"          # Idioma dos posts: en | pt-BR | es

topics:
  rotation: "alternating"
  items:
    - name: "Artificial Intelligence"
      keywords: [...]
    - name: "International Financial Markets"
      keywords: [...]

approval:
  email: "seu@email.com"  # Para onde vai o rascunho

schedule:
  generate_time: "06:00"
  publish_time:  "09:00"
  timezone: "America/Sao_Paulo"
```

> O `config.yaml` controla **todo o comportamento** do agente. Nenhum valor fica hardcoded no código — isso permite usar o mesmo projeto para múltiplos usuários/empresas, cada um com seu próprio `config.yaml`.

### 2. `.env` — credenciais e segredos

```bash
# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Tavily
TAVILY_API_KEY=tvly-...

# LinkedIn (obtidos nos passos abaixo)
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=        # preenchido pelo script de setup
LINKEDIN_PERSON_URN=          # preenchido pelo script de setup

# Gmail
SMTP_USER=seu@gmail.com
SMTP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# URL pública do Railway (após o deploy)
APP_BASE_URL=https://seu-app.railway.app

# Protege os endpoints de trigger manual
TRIGGER_SECRET=string-aleatoria-segura
```

---

## Setup do LinkedIn (uma vez)

### Passo 1 — Criar o app no LinkedIn Developer

1. Acesse [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps)
2. Clique em **Create app**
3. Preencha nome, associe à sua página do LinkedIn, adicione um logo
4. Na aba **Products**, solicite **"Share on LinkedIn"** (aprovação instantânea)
5. Na aba **Auth**:
   - Copie o `Client ID` e `Client Secret` → cole no `.env`
   - Em **Authorized redirect URLs**, adicione exatamente:
     ```
     http://localhost:8888/callback
     ```

### Passo 2 — Gerar o token de acesso

```bash
python scripts/setup_linkedin_auth.py
```

O script abre o navegador, você autoriza, e ele imprime:
```
LINKEDIN_ACCESS_TOKEN=AQX...
LINKEDIN_PERSON_URN=urn:li:person:...
```

Cole esses valores no `.env`.

> O token expira em **60 dias**. Rode o script novamente antes de vencer.

---

## Setup do Gmail (App Password)

1. Acesse [myaccount.google.com/security](https://myaccount.google.com/security)
2. Em **Verificação em 2 etapas** → **Senhas de app**
3. Selecione "Outro (nome personalizado)" → digite "LinkedIn Agent"
4. Copie a senha gerada (formato `xxxx xxxx xxxx xxxx`) → cole em `SMTP_APP_PASSWORD`

---

## Rodando localmente

```bash
# Carrega o .env automaticamente via python-dotenv
python main.py
```

O servidor sobe em `http://localhost:8000`.

### Testar sem esperar o horário agendado

```bash
# Força geração de um rascunho agora
curl "http://localhost:8000/trigger/generate?secret=SEU_TRIGGER_SECRET"

# Força publicação (se houver post aprovado)
curl "http://localhost:8000/trigger/publish?secret=SEU_TRIGGER_SECRET"
```

---

## Deploy no Railway

### Passo 1 — Conectar o repositório

1. Acesse [railway.app](https://railway.app) → **New Project**
2. Selecione **Deploy from GitHub repo**
3. Escolha este repositório

### Passo 2 — Configurar variáveis de ambiente

No painel do Railway → seu projeto → **Variables**, adicione todas as variáveis do `.env` (exceto `APP_BASE_URL`, que você preencherá após o primeiro deploy).

### Passo 3 — Obter a URL pública

Após o deploy, Railway gera uma URL como `seu-app.railway.app`.  
Adicione essa URL como variável:
```
APP_BASE_URL=https://seu-app.railway.app
```

### Passo 4 — Adicionar o volume persistente (banco de dados)

No Railway → seu projeto → **Add Volume** → monte em `/app/data`.  
Isso garante que o SQLite sobreviva a redeploys.

---

## Fluxo de aprovação

1. Às 06:00 BRT você recebe um e-mail com o rascunho
2. Clica no link → abre a página de revisão
3. Você escolhe:
   - **Aprovar** → post publicado às 09:00
   - **Pedir Reescrita** → digita o feedback, novo rascunho chega por e-mail em ~2 minutos
4. Máximo de 3 reescritas por post (configurável em `approval.max_rewrites`)
5. Se nenhuma ação for tomada até as 09:00, o post **não** é publicado (comportamento padrão)

---

## Segurança e copyright

O agente aplica duas camadas de proteção:

| Camada | O que verifica |
|---|---|
| Prompt de geração | Instrui o Claude a parafrasear, nunca copiar; citar fontes; não dar conselhos financeiros |
| Revisão de segurança | Segundo Claude (Haiku, mais rápido) verifica copyright, linguagem de conselho financeiro, conteúdo político e afirmações sem base |

Posts bloqueados na revisão de segurança são descartados — você recebe um log de erro, mas nada é enviado para aprovação.

---

## Configurando para outro usuário ou empresa

1. Fork (ou copie) este repositório
2. Edite `config.yaml` com os dados do novo usuário
3. Configure um novo `.env` com as credenciais dele
4. Faça deploy num novo projeto Railway

Não há nenhum valor específico de usuário no código — tudo vem do `config.yaml`.

---

## Estrutura do projeto

```
Agente-Linkedin-pessoal/
├── config/
│   ├── schema.py              # Validação Pydantic de todo o config.yaml
│   └── loader.py              # Carrega config.yaml em runtime
├── agent/
│   ├── researcher.py          # Busca Tavily → artigos estruturados
│   ├── writer.py              # Gera post com Claude (com cache de prompt)
│   ├── safety.py              # Revisão de copyright/segurança (Claude Haiku)
│   ├── scheduler_logic.py     # Rotação de tópicos e formatos
│   └── linkedin_publisher.py  # Publica via LinkedIn REST API v2
├── notifier/
│   └── email_notifier.py      # E-mails HTML via Gmail SMTP
├── web/
│   ├── app.py                 # FastAPI + APScheduler (orquestrador central)
│   └── templates/review.html  # Página de aprovação
├── database/
│   └── models.py              # SQLAlchemy + SQLite (posts, estado de tópicos)
├── scripts/
│   └── setup_linkedin_auth.py # OAuth LinkedIn (rodar uma vez)
├── config.yaml.example        # Template de configuração
├── .env.example               # Template de variáveis de ambiente
├── Dockerfile                 # Para Railway
├── requirements.txt
└── main.py                    # Entry point (Uvicorn)
```

---

## Custo estimado

| Serviço | Custo mensal |
|---|---|
| Railway (web app) | Gratuito (free tier) |
| Tavily API | Gratuito (até 1.000 buscas) |
| Claude API — 20 posts/mês | ~US$ 0,06 |
| Gmail SMTP | Gratuito |
| LinkedIn API | Gratuito |
| **Total** | **~US$ 0,06/mês** |
