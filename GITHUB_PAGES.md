# 🌐 Vitrine grátis no GitHub Pages

O GitHub Pages **só serve arquivos estáticos** — ele hospeda a **landing page** (vitrine)
de graça, mas **não roda** os agentes, o banco de dados nem a Stripe. Por isso a
arquitetura é dividida:

```
GitHub Pages (grátis, estático)          Backend (servidor pequeno)
┌────────────────────────────┐           ┌─────────────────────────────┐
│  Landing / vitrine (docs/)  │  ── API ▶ │  FastAPI: agentes + carteira │
│  cadastro, botões de compra │           │  Stripe, Postgres, OpenRouter│
└────────────────────────────┘           └─────────────────────────────┘
        user.github.io                     Railway / Render / Vercel
```

> Sem o backend no ar, a vitrine aparece bonita mas os botões mostram
> "backend ainda não configurado". A vitrine **não** faz o pagamento sozinha —
> ela só chama o backend (onde as chaves ficam seguras).

## Passo 1 — Publicar a vitrine (2 cliques, grátis)

A vitrine já está pronta na pasta [`docs/`](./docs/).

1. Faça o merge deste PR na `main` (a vitrine precisa estar na branch padrão).
2. No GitHub: **Settings → Pages → Build and deployment**:
   - **Source:** Deploy from a branch
   - **Branch:** `main` · **Folder:** `/docs` → **Save**
3. Aguarde ~1 min. Sua vitrine fica no ar em:
   `https://SEU-USUARIO.github.io/500-ai-agents-projects/`

Pronto — você já tem uma **URL pública grátis** da vitrine.

## Passo 2 — Subir o backend (o que fatura)

Escolha um (todos têm plano grátis/barato):
- **Railway/Render** → veja [`DEPLOY.md`](./DEPLOY.md) (mais simples, servidor sempre ligado).
- **Vercel** → veja [`VERCEL.md`](./VERCEL.md) (serverless; exige Postgres externo).

Ao final você terá a URL do backend, ex.: `https://seu-app.up.railway.app`.

## Passo 3 — Conectar a vitrine ao backend

1. Edite [`docs/config.js`](./docs/config.js) e cole a URL do backend:
   ```js
   window.API_BASE = "https://seu-app.up.railway.app";
   ```
2. No backend, autorize a origem da vitrine (CORS) definindo a env var:
   ```
   CORS_ORIGINS=https://SEU-USUARIO.github.io
   ```
   (O padrão já é `*`, que funciona, mas restringir é mais seguro em produção.)
3. Commit + push. O GitHub Pages atualiza sozinho.

Agora o cadastro e a compra de créditos na vitrine funcionam de ponta a ponta.

## Alternativas ao GitHub Pages (mesma ideia, estático grátis)
- **Cloudflare Pages** e **Netlify** — aponte para a pasta `docs/`.
- Ou sirva a landing **pelo próprio backend** (ele já tem uma landing em `/`),
  dispensando o GitHub Pages — útil se quiser tudo em um domínio só.
