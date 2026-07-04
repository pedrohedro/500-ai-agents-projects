# 🚀 Guia de Deploy — Colocar a plataforma no ar e faturando

Este guia leva a plataforma do zero ao **primeiro pagamento real** em cerca de 1–2 horas.
Escolha **uma** das opções de hospedagem (Railway é a mais rápida). Todos os comandos
são para copiar e colar. O contexto de build é a **raiz do repositório** (o `Dockerfile`
está em `monetization_platform/Dockerfile` mas importa os 4 agentes da raiz).

---

## 0. Pré-requisitos (15 min)

Crie estas 2 contas e pegue as chaves:

| Serviço | Onde pegar | Variável |
|---|---|---|
| **OpenRouter** (modelos open-source) | <https://openrouter.ai/keys> | `OPENROUTER_API_KEY` |
| **Stripe** (pagamentos) | <https://dashboard.stripe.com/apikeys> | `STRIPE_API_KEY` |

> Dica: comece com a chave **de teste** da Stripe (`sk_test_...`) para validar o fluxo
> sem cobrar de verdade. Depois troque para a de produção (`sk_live_...`).

Coloque US$5–10 de crédito na OpenRouter — dá para milhares de chamadas nos modelos baratos.

---

## Opção A — Railway (recomendado, mais rápido)

1. Instale a CLI e faça login:
   ```bash
   npm i -g @railway/cli
   railway login
   ```
2. Na raiz do repositório, inicialize o projeto e adicione um Postgres:
   ```bash
   railway init
   railway add --database postgres
   ```
3. Configure as variáveis (troque os valores):
   ```bash
   railway variables \
     --set "LLM_PROVIDER=openrouter" \
     --set "OPENROUTER_API_KEY=sk-or-..." \
     --set "OPENROUTER_MODEL=deepseek/deepseek-v4-flash" \
     --set "STRIPE_API_KEY=sk_test_..." \
     --set "SIGNUP_BONUS_CREDITS=25"
   ```
   (O `DATABASE_URL` é injetado automaticamente pelo plugin Postgres.)
4. Faça o deploy:
   ```bash
   railway up
   ```
5. Gere o domínio público e guarde a URL:
   ```bash
   railway domain
   ```
6. Ajuste a URL base e reinicie:
   ```bash
   railway variables --set "BASE_URL=https://SEU-DOMINIO.up.railway.app"
   railway up
   ```

Pule para a seção **"Configurar o webhook da Stripe"**.

---

## Opção B — Render (via blueprint `render.yaml`)

1. Suba o repositório para o GitHub (já está).
2. Em <https://dashboard.render.com> → **New** → **Blueprint** → selecione o repo.
   O Render lê o `monetization_platform/render.yaml` e cria o web service + Postgres.
3. Em **Environment**, defina:
   ```
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-...
   OPENROUTER_MODEL=deepseek/deepseek-v4-flash
   STRIPE_API_KEY=sk_test_...
   BASE_URL=https://SEU-SERVICO.onrender.com
   ```
   (`DATABASE_URL` é ligado automaticamente ao banco do blueprint.)
4. Clique em **Apply** / **Deploy**.

Pule para **"Configurar o webhook da Stripe"**.

---

## Opção C — Docker / qualquer VPS

```bash
# na raiz do repositório
docker build -f monetization_platform/Dockerfile -t agent-api .

docker run -d -p 8000:8000 \
  -e LLM_PROVIDER=openrouter \
  -e OPENROUTER_API_KEY=sk-or-... \
  -e OPENROUTER_MODEL=deepseek/deepseek-v4-flash \
  -e STRIPE_API_KEY=sk_test_... \
  -e DATABASE_URL="postgresql://user:pass@host:5432/db" \
  -e BASE_URL=https://seu-dominio.com \
  --name agent-api agent-api
```

Coloque um proxy reverso (Caddy/Nginx) com HTTPS na frente e aponte o domínio.

Para desenvolvimento local com Postgres embutido:
```bash
cd monetization_platform && docker compose up
```

---

## Configurar o webhook da Stripe (o que credita a carteira sozinho)

1. Em **Stripe → Developers → Webhooks → Add endpoint**:
   - URL: `https://SEU-DOMINIO/billing/webhook`
   - Evento: `checkout.session.completed`
2. Copie o **Signing secret** (`whsec_...`) e adicione na hospedagem:
   ```bash
   # Railway
   railway variables --set "STRIPE_WEBHOOK_SECRET=whsec_..." && railway up
   # Render: adicione STRIPE_WEBHOOK_SECRET no painel Environment
   ```
3. Defina também (opcional, mas recomendado) as URLs de retorno:
   ```
   STRIPE_SUCCESS_URL=https://SEU-DOMINIO/dashboard?paid=1
   STRIPE_CANCEL_URL=https://SEU-DOMINIO/?canceled=1
   ```

> Assim que `STRIPE_API_KEY` está setada, o **modo mock é desligado automaticamente**
> e o endpoint de teste `/billing/simulate-payment` é desativado. A partir daqui,
> pagamentos são reais.

---

## Teste de fumaça (prove que o dinheiro entra)

Use o cartão de teste da Stripe: **`4242 4242 4242 4242`**, validade futura, CVC qualquer.

```bash
BASE=https://SEU-DOMINIO

# 1) Verifique que subiu e está em produção
curl -s $BASE/health
# espere: "stripe_enabled": true, "llm_provider": "openrouter"

# 2) Crie um usuário (guarde a api_key retornada)
curl -s -X POST $BASE/auth/signup -H 'content-type: application/json' \
  -d '{"email":"voce@exemplo.com"}'

# 3) Abra a landing no navegador, faça login e clique em "Comprar créditos".
#    Pague com o cartão 4242... -> o webhook credita a carteira automaticamente.

# 4) Chame um agente com a sua api_key
curl -s -X POST $BASE/v1/marketing/generate \
  -H "Authorization: Bearer SUA_API_KEY" -H 'content-type: application/json' \
  -d '{"topic":"consultoria financeira","audience":"pequenas empresas"}'
# a resposta traz o conteúdo + usage (créditos descontados)
```

Se o passo 3 creditou a carteira e o passo 4 descontou, **está faturando.** ✅

---

## Checklist final

- [ ] `curl /health` mostra `stripe_enabled: true` e `llm_provider: openrouter`
- [ ] Landing abre em `https://SEU-DOMINIO/`
- [ ] Compra com cartão de teste credita a carteira (via webhook)
- [ ] Chamada a um `/v1/...` desconta créditos e retorna resultado
- [ ] Trocou `sk_test_` por `sk_live_` quando estiver pronto para cobrar de verdade
- [ ] Monitorou o custo na OpenRouter vs. receita (margem — ver `README.md`)

Dúvidas de precificação e margem: veja [`GO_TO_MARKET/pricing-and-margins.md`](./GO_TO_MARKET/pricing-and-margins.md).
