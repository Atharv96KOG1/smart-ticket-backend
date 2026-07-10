# Smart Ticket Router

Reads a raw support message and returns a validated, schema-conformant routing
decision — category, priority, assigned team, one-line reasoning — with
deterministic tie-breaking and a defense-in-depth reliability layer around the LLM
call.

```json
{
  "category": "Billing",
  "priority": "High",
  "assigned_team": "Billing Team",
  "reasoning": "Customer was double-charged and requests an urgent refund."
}
```

## Stack

FastAPI · Pydantic (the JSON-schema/validation layer) · OpenAI (GPT) · a Rich-powered CLI.

## Architecture

```
CLI (cli.py) ──┬─▶ core/router.py  (direct import, no server needed)
               └─▶ FastAPI /route (--api flag) ──▶ api/routes.py ──▶ core/router.py

core/router.py:
  core/guardrails.py  → strip quoted threads, head/tail trim, reject blank
  core/prompt.py      → system prompt + few-shot examples + decision rules
  llm/client.py       → OpenAI call, temperature=0, retries rate-limits/timeouts with backoff
  llm/exceptions.py   → typed provider errors (auth/rate-limit/connection)
  schemas/ticket.py   → Pydantic contract (category/priority/team enums)
  router.py           → parse → validate → retry-once → safe fallback
```

The LLM is the only unreliable step. Everything else — guardrails, JSON parsing,
Pydantic validation, retry, fallback, the deterministic escalation-only priority
rule — is ordinary code wrapping that one unreliable call.

### Decision rules baked into the prompt

- **Payment/billing issue? Always High.** Charges, refunds, failed payments,
  unauthorized transactions — money at risk is never downgraded to Medium or Low,
  regardless of tone. This is rule 1, checked before anything else.
- **Two categories fit?** Route by blocking root cause, then a fixed precedence
  order: billing (payment) > security access > login access > bug > technical >
  complaint > feature > general. The loser goes in `secondary_category`, never
  discarded.
- **Multiple issues, different urgency?** Priority = the **highest**, never the
  average — under-prioritizing a real High ticket is far costlier than
  over-prioritizing a Low one.
- **Anger alone doesn't raise priority** — only impact does (money, downtime,
  security, blocked work). A small deterministic post-rule in `guardrails.py` can
  only *raise* priority on hard signals (payment/refund language, "data loss",
  "suspicious login", ...), never lower it — a safety net over the model.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your real OPENAI_API_KEY
```

## Run it

**CLI, no server needed** (imports the router directly):

```bash
python cli.py route          # interactively route one ticket
python cli.py demo           # batch-route the 20 sample tickets + timing
```

**FastAPI server**, for the same CLI to hit over HTTP, or any other client:

```bash
uvicorn smart_ticket_router.main:app --reload --app-dir src
# in another terminal:
python cli.py route --api
python cli.py demo --api
curl -X POST localhost:8000/route -H "content-type: application/json" \
     -d '{"message": "I was charged twice this month, refund me now!"}'
```

Interactive API docs: `http://127.0.0.1:8000/docs`

## Frontend

The web UI lives in a separate repo (`smart-ticket-frontend`) and talks to this
API over HTTP. CORS is enabled via `CORSMiddleware`; allowed origins default to
common local dev ports (`localhost:3000`, `localhost:5173`) and can be
overridden with the `ALLOWED_ORIGINS` env var (comma-separated). `GET /data`
serves `data/sample_tickets.json` for the frontend's sample-ticket picker.

## Reliability guarantee

The caller always gets a schema-valid `TicketRoute` — either a real classification
or the documented safe fallback (`General Inquiry` / `Medium` / `Tier-1 Support`,
flagged low-confidence for human review). Malformed JSON from the model never
reaches the caller.

## Edge cases covered

| Case | Where |
|---|---|
| Blank input | Rejected client-side in the CLI before any call is made; server re-checks too |
| Oversized message | `guardrails.py` strips quoted email threads, then keeps head+tail (never blind-truncates) |
| Ambiguous / two categories | Prompt precedence rule + `secondary_category` field |
| Multi-issue priority | Prompt take-the-highest rule |
| Angry tone, no real impact | Prompt rule 3 — tone alone never raises priority |
| Bad API key / rate limit / network drop | `llm/client.py` raises typed errors → clean HTTP status / CLI message, never a crash |
| Rate limit hit mid-request | Retried with exponential backoff (respecting `Retry-After` if provided) before surfacing a 429 |

## Repo layout

```
backend/
├── src/
│   └── smart_ticket_router/
│       ├── main.py            FastAPI app factory (CORS, static /data mount, router wiring)
│       ├── config.py          env-based settings (model, char limits, allowed origins)
│       ├── api/
│       │   └── routes.py      /health, /route endpoints
│       ├── core/
│       │   ├── router.py      parse → validate → retry-once → safe fallback pipeline
│       │   ├── prompt.py      system prompt + few-shot examples
│       │   └── guardrails.py  length/thread-strip/escalation rules
│       ├── llm/
│       │   ├── client.py      OpenAI client wrapper, retry + backoff
│       │   └── exceptions.py  typed provider errors
│       └── schemas/
│           ├── ticket.py       Pydantic contract (category/priority/team enums)
│           └── requests.py     API request body
├── cli.py                     CLI (direct or --api mode)
├── data/sample_tickets.json   20-ticket demo set
├── .env.example
└── requirements.txt
```
