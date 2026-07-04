# ▲ Deploy no Vercel

O repositório já vem pronto para o Vercel:

- `vercel.json` — roteia todo request para a função Python.
- `api/index.py` — entrypoint ASGI (expõe o app FastAPI da plataforma).
- `requirements.txt` (raiz) — dependências de runtime (sem uvicorn/pytest).
- `.vercelignore` — mantém o bundle pequeno (ignora `.venv`, `tests`, `*.db`…).

> **Importante (Vercel é serverless):** não há disco persistente, então **SQLite não
> serve** — você **precisa de um Postgres externo** (Vercel Postgres, Neon ou Supabase).
> O app já normaliza URLs `postgres://` automaticamente.

---

## Pré-requisitos (você cria — eu não tenho como criar no seu nome)

1. Conta no **Vercel**: <https://vercel.com/signup>
2. Um **Postgres gerenciado** e sua connection string:
   - Vercel Postgres (Storage no painel), ou
   - Neon <https://neon.tech>, ou Supabase <https://supabase.com>
3. Chave da **OpenRouter**: <https://openrouter.ai/keys>
4. Chave da **Stripe**: <https://dashboard.stripe.com/apikeys>

---

## Caminho 1 — Painel do Vercel (recomendado, sem compartilhar segredos comigo)

1. <https://vercel.com/new> → importe este repositório do GitHub.
2. **Root Directory:** deixe a raiz do repositório (a `/`), pois a função importa os
   4 pacotes de agente que ficam na raiz. **Não** aponte para `monetization_platform/`.
3. Em **Environment Variables**, adicione:
   ```
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-...
   OPENROUTER_MODEL=deepseek/deepseek-v4-flash
   STRIPE_API_KEY=sk_test_...
   DATABASE_URL=postgres://usuario:senha@host:5432/db
   BASE_URL=https://SEU-PROJETO.vercel.app
   SIGNUP_BONUS_CREDITS=25
   ```
4. **Deploy.** O Vercel te dá a URL pública (ex.: `https://seu-projeto.vercel.app`).
5. Configure o **webhook da Stripe** apontando para
   `https://SEU-PROJETO.vercel.app/billing/webhook` (evento `checkout.session.completed`)
   e cole o `whsec_...` em `STRIPE_WEBHOOK_SECRET` nas env vars → Redeploy.
6. Teste: abra a URL (landing), cadastre-se, compre com o cartão de teste
   `4242 4242 4242 4242`, confirme o crédito e chame um agente.

## Caminho 2 — Eu faço o deploy a partir daqui (via Vercel CLI)

Para isso preciso que você adicione um **`VERCEL_TOKEN`** (e as chaves acima) como
**Secrets do Cloud Agent** no Cursor (Dashboard → Cloud Agents → Secrets). Aí eu rodo:
```bash
npm i -g vercel
vercel pull --yes --token $VERCEL_TOKEN
vercel deploy --prod --token $VERCEL_TOKEN
```
e configuro as env vars via `vercel env add`. (Você ainda precisa criar o Postgres e
me passar o `DATABASE_URL`.)

---

## Limitações do Vercel para este app (seja realista)

O Vercel funciona, mas é serverless — para um SaaS com banco + chamadas de IA, um
servidor sempre-ligado (Railway/Render, ver `monetization_platform/DEPLOY.md`) tende
a ser mais simples. Pontos de atenção no Vercel:

- **Postgres externo obrigatório** (SQLite não persiste entre invocações).
- **Timeout de função** (60s aqui; planos maiores permitem mais) — ok para os modelos
  rápidos, mas chamadas muito longas podem estourar.
- **Tamanho do bundle** (limite ~250MB): por isso o `.vercelignore` remove testes e
  artefatos. Se estourar, mova para Railway/Render.
- **Cold start**: a primeira requisição após ociosidade é mais lenta.

Se qualquer um desses te incomodar, o `DEPLOY.md` tem Railway/Render prontos com os
mesmos comandos.
