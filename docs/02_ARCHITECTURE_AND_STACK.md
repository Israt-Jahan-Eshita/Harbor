# 02 — Architecture and Stack

## 1. Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3 | One API service |
| Database | PostgreSQL | Local PostgreSQL in Docker for dev and tests. Supabase in production (pooler connection string). No SQLite. |
| Tools layer | FastMCP | Thin wrapper over pure functions in `core/` |
| LLM and speech | Groq (`whisper-large-v3` for speech, `openai/gpt-oss-120b` for language), a Gemini vision model for prescriptions | Model names come from env vars. Verify current model ids before use. |
| Fuzzy match | rapidfuzz | Ingredient alias matching |
| Push | `pywebpush` (VAPID), email fallback, in-app polling | iOS push needs the PWA installed, so polling is the safety net |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS | PWA, Bangla-first, light and dark mode |
| Tests | pytest (backend), Vitest or Jest plus Playwright (frontend) | See `docs/05` |
| Hosting | Render (frontend service, backend service), Supabase (database) | |

**Versions:** do not guess. Look up current stable versions from the package registries when bootstrapping and record them in the README. Verify every API you use against the installed version.

## 2. Layering rules (enforced in review)

```
 api/      thin HTTP handlers: auth, validation, call services, shape responses
 core/     PURE PYTHON: rules, shared-pot, scoring, inventory, qty parsing, bazar,
           reminders state machine, validator, templates. NO network, NO LLM, NO env reads.
 llm/      untrusted: speech, vision, parsing, explanation, agent loop. Always parsed + validated.
 mcp/      FastMCP server exposing core/ functions as tools
 seed/     JSON data + loader
```

- `core/` imports nothing from `llm/`, `api/` or network libraries. Unit tests for `core/` run with no network and no database where possible (functions take plain data objects).
- `llm/` never writes to safety-relevant tables directly. It returns proposals. The caregiver confirms, then `api/` writes.
- Every safety decision returns a **trace** (list of rule ids and reasons) so it can be shown in the UI and explained in the presentation.

## 3. System diagram

```
 Caregiver (Next.js PWA)               Patient phone  /patient/[token]
   text / voice / photo / buttons         one big button, polling + push
              |                                    |
              v                                    v
 +------------------------------ FastAPI ------------------------------+
 | api/*  (auth by household code + PIN, patient token, validation)     |
 |                                                                      |
 |  llm/ (untrusted)                  core/ (trusted, pure Python)      |
 |  speech -> text                    check_dish_safe                   |
 |  text -> event proposals           find_shared_pot_dishes            |
 |  photo -> draft medicines          score_dishes                      |
 |  agent loop (tools only)           inventory, qty, bazar, reminders  |
 |  Bangla explanation                validator, templates              |
 |            |                              ^                          |
 |            +--------> mcp/ tools ---------+                          |
 +------------------------------------|---------------------------------+
                                      v
                            PostgreSQL (Supabase in prod)

 External pinger --> POST /internal/tick (header X-Tick-Secret) --> idempotent jobs
```

## 4. Repository layout

```
harbor/
  README.md
  AGENT_PROMPT.md
  docs/                     (all planning docs, ENGINE_LOGIC_BN.md, ISSUES.md, AUDIT_REPORT.md)
  docker-compose.yml        (local PostgreSQL)
  backend/
    requirements.txt  pyproject.toml (optional)  alembic.ini  alembic/
    .env.example
    app/
      main.py  config.py  db.py  models.py  schemas.py  deps.py  errors.py
      api/  households.py members.py prescriptions.py events.py menu.py bazar.py
            stock.py reminders.py push.py dashboard.py engine.py eval.py internal.py
      core/ rules.py shared_pot.py scoring.py inventory.py bangla_qty.py
            bazar.py reminders.py validator.py templates.py prices.py
      llm/  client.py prompts.py extract_prescription.py parse_events.py
            explain.py agent.py
      mcp/  server.py
      seed/ ingredients.json recipes.json rules.json drug_class_map.json
            aliases.json prices.json diet_presets.json load.py
    tests/  unit/ integration/ llm_contract/ scenarios/
  eval/     cases.json run_eval.py baseline.py results.md
  frontend/
    .env.example
    app/ (routes, see docs/04)
    components/ lib/ messages/ (bn.json, en.json) styles/ public/
```

## 5. Environment variables

Backend (`backend/.env.example`, names only, never values):
`DATABASE_URL`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL`, `STT_MODEL`, `VISION_MODEL`, `CORS_ORIGINS`, `SESSION_SECRET`, `TICK_SECRET`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `TZ=Asia/Dhaka`, `ENV` (`dev|test|prod`), score weights and reminder offsets as optional overrides.

Frontend: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_VAPID_PUBLIC_KEY`.

Config is validated at startup. Missing required values fail fast with a clear message.

## 6. Data model

The full table list and columns are in `docs/SPEC_FULL.md` section 6. Notes:
- UUID primary keys, timezone-aware timestamps, display in Asia/Dhaka.
- Inventory is an append-only event log; stock is the signed sum.
- `llm_calls` logs every model call (task, model, input summary, output, validated flag, latency).
- Prescription images are not stored.

## 7. Scheduling

Free Render instances sleep after inactivity, so an in-process scheduler will not fire. Use the **tick** design: `POST /internal/tick` runs all due work. Every job is idempotent and driven by database state. An external pinger (any service that can call a URL every minute) hits it and also keeps the service warm. An admin-only `now` override on the tick endpoint lets the demo show reminders and escalation without waiting.

## 8. Deployment summary

- **Supabase:** create a project, use the pooler connection string. Run Alembic migrations and the seed loader. Free projects can pause after inactivity, so open the dashboard before the demo. Ask the owner before touching production.
- **Render backend:** Python web service, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/healthz`.
- **Render frontend:** Node web service, build `npm ci && npm run build`, start `npm start`. `NEXT_PUBLIC_*` variables are needed at build time.
- CORS must list the exact frontend origin. HTTPS is provided by Render. Never commit keys.

## 9. Security and privacy notes

- Household access code + PIN gives a signed session. Patient links use an unguessable per-member token that can only read and confirm that member's doses. State in the README that real authentication is a production requirement.
- Rate-limit the LLM-backed endpoints.
- Do not log full prescription content or audio. Log summaries and ids.
- Notifications carry generic text only.
- CORS restricted, secrets only in env, input validated by Pydantic everywhere.

## 10. Observability

- Request id on every response and in logs.
- `llm_calls` table for audit and debugging.
- Structured logs; error responses use `{ "code", "message", "details" }`.
- `/healthz` checks database connectivity.

