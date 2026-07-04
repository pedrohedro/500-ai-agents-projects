# Agent API Cloud — Monetization Platform

Turn the four AI agents in this repository into a single, deployable, **paid SaaS
product**. Customers sign up, get an API key, buy credits (Stripe), and call the
agents via a unified, metered API. Money is credited automatically on payment and
credits are metered per use.

It runs **end-to-end with no real keys** (mock Stripe + mock LLM), so the whole
money loop is testable locally and in CI. Add real Stripe + OpenRouter keys and
deploy to go live.

```
Landing page  ─▶  Signup (API key + free credits)
                     │
                     ▼
              Buy credits (Stripe Checkout) ──▶ Webhook ──▶ Wallet credited
                     │
                     ▼
        POST /v1/{marketing|legal|support|hr}   ← Bearer API key
                     │  check credits → run agent → deduct → log usage
                     ▼
        Result JSON  +  immutable usage ledger  (402 when out of credits)
```

## Wrapped agents

| Endpoint | Agent | Integration | Default cost |
|---|---|---|---|
| `POST /v1/marketing/generate` | `marketing_content_agent` | real import (`ContentPipeline`) | 5 credits |
| `POST /v1/legal/review` | `legal_doc_reviewer_agent` | real import (`ReviewPipeline`) | 8 credits |
| `POST /v1/support/chat` | `support_chatbot_agent` | real import (`chatbot.build_agent`) | 1 credit |
| `POST /v1/hr/screen` | `hr_resume_screening_agent` | real import (`ScreeningPipeline`) | 3 credits |

Each agent is wrapped by a **thin adapter** in `adapters/`. If an agent package
ever fails to import (missing optional dep, refactor, etc.) the adapter falls
back to a deterministic **mock adapter** so the platform always runs and always
returns a well-shaped response. The `usage.mock_adapter` flag in every response
tells you which path was taken.

## Quick start (mock mode, no keys)

```bash
cd monetization_platform
/usr/bin/python3 -m virtualenv .venv        # system lacks ensurepip; use virtualenv
.venv/bin/pip install -r requirements.txt

# Run the test suite (all green, no keys needed)
cd .. && monetization_platform/.venv/bin/python -m pytest monetization_platform/tests -v

# Start the API + landing page
monetization_platform/.venv/bin/uvicorn monetization_platform.app:app --port 8000
# open http://localhost:8000  (landing)  and  /dashboard
```

Seed a demo user with credits:

```bash
python -m monetization_platform.cli seed --email demo@example.com --credits 500
```

## The money loop with curl (mock mode)

```bash
B=http://localhost:8000
# 1. Sign up -> API key + free credits
KEY=$(curl -s -X POST $B/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"buyer@example.com"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key'])")

# 2. Buy credits (mock Stripe returns a fake checkout URL)
curl -s -X POST $B/billing/checkout -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"pack_key":"starter"}'

# 3. Simulate the payment (mock-only) -> wallet credited
curl -s -X POST $B/billing/simulate-payment -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"pack_key":"starter"}'

# 4. Call an agent (credits metered per call)
curl -s -X POST $B/v1/marketing/generate -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"topic":"AI for small business"}'

# 5. Balance + usage ledger
curl -s $B/billing/balance -H "Authorization: Bearer $KEY"
```

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | – | Landing page (pricing, signup, docs) |
| GET | `/dashboard` | – (key entered in UI) | Balance + usage dashboard |
| GET | `/health` | – | Liveness + config |
| POST | `/auth/signup` | – | Create account, issue API key (shown once) |
| GET | `/auth/me` | Bearer | Current user + balance |
| GET | `/billing/packs` | – | List credit packs |
| POST | `/billing/checkout` | Bearer | Create Stripe Checkout Session |
| POST | `/billing/webhook` | Stripe sig | Credit wallet on `checkout.session.completed` |
| POST | `/billing/simulate-payment` | Bearer | **Mock-only** simulate a paid checkout |
| GET | `/billing/balance` | Bearer | Balance + recent ledger events |
| POST | `/v1/marketing/generate` | Bearer | Marketing content agent |
| POST | `/v1/legal/review` | Bearer | Legal document reviewer agent |
| POST | `/v1/support/chat` | Bearer | Support RAG chatbot agent |
| POST | `/v1/hr/screen` | Bearer | HR resume screening agent |

Auth is `Authorization: Bearer <api_key>`. Out-of-credits returns **HTTP 402**.

## Data model

- **users** — `id`, `email`, `credits` (cached balance), `created_at`.
- **api_keys** — SHA-256 **hash** of the key only (raw key shown once), `prefix`, `active`.
- **usage_events** — immutable ledger. Each row: `kind` (`credit`/`debit`),
  `agent`, `credits_delta` (signed), `balance_after`, `tokens`, `usd_cost`,
  `description`, `reference`, `created_at`. `SUM(credits_delta)` reconstructs the
  balance, so the wallet and ledger can never drift.

Tables are auto-created on startup (`init_db`). `DATABASE_URL` defaults to SQLite
and upgrades to Postgres transparently (e.g.
`postgresql+psycopg://user:pass@host:5432/db`).

## Pricing & unit economics

All values are env-driven (`config.py` / `.env.example`).

**Credit packs** (retail):

| Pack | Price | Credits | $ / credit |
|---|---|---|---|
| Starter | $19 | 1,000 | $0.0190 |
| Pro | $79 | 5,000 | $0.0158 |
| Business | $299 | 25,000 | $0.0120 |

**Per-agent cost:** marketing 5, legal 8, support 1, hr 3 credits per call.

**Where the margin comes from.** Retail price per credit is ~$0.012–$0.019.
The variable cost of a call is the OpenRouter/OpenAI token cost. Example, a
marketing call on `gpt-4o-mini` (~$0.00015 in / $0.0006 out per 1k tokens) using
~900 tokens costs roughly **$0.0005** in tokens. That call retails at 5 credits ≈
**$0.06–$0.095**. So:

```
gross margin per marketing call ≈ $0.06 − $0.0005  ≈  $0.0595   (~99% on Starter)
```

Even on cheap packs and larger models the markup is deliberately large (retail
credit price ÷ token cost is 50×–200×), which absorbs infra, Stripe fees
(~2.9% + $0.30 per charge, amortized over a whole pack), and support overhead
while keeping healthy margins. Tune the knobs to your model and target margin:

- `CREDIT_PRICE_USD`, `PACK_*_PRICE`, `PACK_*_CREDITS` — retail side.
- `COST_MARKETING` / `COST_LEGAL` / `COST_SUPPORT` / `COST_HR` — credits per call.
- `LLM_MODEL` — pick the model whose token cost fits your margin.

The ledger records real `tokens` and `usd_cost` per call, so you can monitor
actual margin in production from the `usage_events` table.

## Go live in 7 steps

1. **Get an OpenRouter key** at <https://openrouter.ai/keys> and set
   `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY=...`. (OpenRouter is
   OpenAI-API compatible; the platform points the agents' OpenAI client at it via
   `OPENAI_BASE_URL` automatically — no agent code changes.)
2. **Get Stripe keys** at <https://dashboard.stripe.com/apikeys> and set
   `STRIPE_API_KEY=sk_live_...` (or `sk_test_...` first). This automatically
   switches off mock Stripe mode and disables `/billing/simulate-payment`.
3. **Provision a database.** Set `DATABASE_URL` to your Postgres URL (Render/Railway
   provide one). Tables auto-create on boot; or run `python -m monetization_platform.cli init`.
4. **Deploy.** Use the provided `Dockerfile` (build context = repo root),
   `docker-compose.yml`, `render.yaml`, or `Procfile` (Railway/Heroku). Set
   `BASE_URL` to your public URL.
5. **Set the Stripe webhook.** In Stripe → Developers → Webhooks, add
   `https://YOUR_DOMAIN/billing/webhook` for event `checkout.session.completed`,
   copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
6. **Point a domain** at the deployment and update `BASE_URL`,
   `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`.
7. **Smoke test** with a Stripe test card (`4242 4242 4242 4242`): buy a pack,
   confirm the webhook credits the wallet, call an agent, confirm the debit.

### Environment variables the owner must set to go live

| Variable | Required | Purpose |
|---|---|---|
| `LLM_PROVIDER=openrouter` | yes | Use OpenRouter in production |
| `OPENROUTER_API_KEY` | yes | OpenRouter billing/auth |
| `STRIPE_API_KEY` | yes | Enables real Stripe (turns off mock) |
| `STRIPE_WEBHOOK_SECRET` | yes | Verifies webhook signatures |
| `BASE_URL` | yes | Public URL for redirects/links |
| `DATABASE_URL` | recommended | Postgres for production persistence |
| `OPENAI_API_KEY` | alt. to OpenRouter | If `LLM_PROVIDER=openai` |

Everything else has a sensible default.

## Deployment files

- `Dockerfile` — build context must be the **repo root** so the sibling agent
  packages are copied in: `docker build -f monetization_platform/Dockerfile -t agent-api-cloud .`
- `docker-compose.yml` — app + optional Postgres (commented; SQLite by default).
- `render.yaml` — Render blueprint (web service + managed Postgres).
- `Procfile` — Railway/Heroku (`web` + `release` migrate step).

## Testing

```bash
monetization_platform/.venv/bin/python -m pytest monetization_platform/tests -v
```

Covers: signup+auth, API-key hashing, wallet credit/debit + ledger reconstruction,
Stripe checkout (mock), webhook + simulate-payment crediting, all four metered
agent endpoints, 402 when out of credits, and landing-page render — all with no
real keys.
