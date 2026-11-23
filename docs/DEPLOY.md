# Harbor — Deployment Guide (Supabase + Render)

This document prepares **Phase 7** deployment of Harbor across **Supabase** (PostgreSQL) and **Render** (FastAPI backend + Next.js frontend). Do not apply these steps against production credentials without explicit owner approval.

---

## 1. Architecture Overview for Cloud Hosting

| Service | Host | Root Directory | Purpose |
| :--- | :--- | :--- | :--- |
| PostgreSQL Database | Supabase | — | Managed Postgres 16+/18 instance (`19` Alembic tables + reference/demo seed) |
| Backend Web Service (`harbor-api`) | Render (Python) | `backend/` | FastAPI REST API, deterministic `core/`, FastMCP agent, `/internal/tick` |
| Frontend Web Service (`harbor-web`) | Render (Node) | `frontend/` | Next.js `16.4.6` PWA (`next build --webpack` + `next start`) |
| External Pinger | cron-job.org / UptimeRobot | — | Calls `POST https://<api>/internal/tick` every minute with `X-Tick-Secret` |

---

## 2. Supabase Database Setup

1. Create a Supabase project (choose a nearby region such as Singapore `ap-southeast-1`).
2. Open **Project Settings -> Database -> Connection string -> Session Pooler** (port `5432`, IPv4-compatible for Render free instances).
3. Format the SQLAlchemy `psycopg` v3 URL:
   ```text
   postgresql+psycopg://postgres.<PROJECT_REF>:<URL_ENCODED_PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
   ```
   - Use **Session Pooler (`5432`)** rather than Transaction Pooler (`6543`) so SQLAlchemy server-side statements and Alembic locks behave reliably.
   - Note: Supabase free tier projects pause after inactivity; open the Supabase dashboard before a live demo to wake the DB.

### Run Migrations & Seed Data (Once Before First Traffic)

From a machine or Render Shell configured with the production `DATABASE_URL`:

```powershell
cd backend
alembic upgrade head
python -m app.seed.load
```

Expected verified reference seed counts: `51` ingredients, `172` aliases, `40` recipes, `4` drug-food rules, `4` diet presets, and demo household `DEMO26` (PIN `1234`).

---

## 3. Generate Production Secrets & VAPID Keys

Run once locally (do **not** reuse local dev secrets in production):

```powershell
# Random secrets (SESSION_SECRET >= 16 chars, TICK_SECRET >= 8 chars)
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32)); print('TICK_SECRET=' + secrets.token_urlsafe(24))"

# Generate Web Push VAPID ECDSA P-256 keys (from backend .venv)
python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('VAPID_PUBLIC_KEY=' + v.public_key_urlsafe_base64()); print('VAPID_PRIVATE_KEY=' + v.private_key_urlsafe_base64())"
```

*(Alternatively generate `SESSION_SECRET` / `TICK_SECRET` automatically via `render.yaml` `generateValue: true`.)*

---

## 4. Render Deployment (`render.yaml` or Manual Dashboard)

A ready-to-use Blueprint is provided in [`render.yaml`](../render.yaml).

### A. Backend Service (`harbor-api`)

- **Runtime:** Python `3.11.9` (pinned via `PYTHON_VERSION` in `render.yaml`)
- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/healthz` (verifies FastAPI + PostgreSQL connectivity `SELECT 1`)

#### Required Backend Environment Variables

| Variable | Example / Value | Notes |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.11.9` | Pinned in `render.yaml` to avoid wheel compilation drift |
| `ENV` | `prod` | Enforces strict non-dev settings & disables public `/docs` |
| `TZ` | `Asia/Dhaka` | Default clinic/mealtime timezone |
| `DATABASE_URL` | `postgresql+psycopg://...` | Supabase Session Pooler URI (`pool_size=3`, SQLite rejected) |
| `GROQ_API_KEY` | `gsk_...` | Groq Llama/GPT-OSS + Whisper STT |
| `GEMINI_API_KEY` | `AIza...` | Gemini `gemini-3.5-flash` vision for prescriptions |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Bounded MCP agent reasoning model (`reasoning_effort=low`) |
| `LLM_FAST_MODEL` | `llama-3.1-8b-instant` | Fast low-token model for `parse_events` and `menu_explain` |
| `STT_MODEL` | `whisper-large-v3` | Speech-to-text model ID |
| `VISION_MODEL` | `gemini-3.5-flash` | Prescription extraction model ID (`ISSUE-007`) |
| `GROQ_DAILY_TOKEN_CAP` | `150000` | In-memory daily token guard + 15m cooldown on HTTP 429 |
| `ALLOW_DEMO_TICK_OVERRIDE` | `false` | Set `true` temporarily only during live demo time-simulation |
| `CORS_ORIGINS` | `https://harbor-web.onrender.com` | **Must match exact frontend origin** (comma-separated if multiple, no trailing slash) |
| `SESSION_SECRET` | `<32+ char random>` | Signs caregiver auth & HMAC `confirmation_token` |
| `TICK_SECRET` | `<24+ char random>` | Authorizes `POST /internal/tick` via `X-Tick-Secret` |
| `VAPID_PUBLIC_KEY` | `<base64url public>` | Matches frontend `NEXT_PUBLIC_VAPID_PUBLIC_KEY` |
| `VAPID_PRIVATE_KEY` | `<base64url private>` | Used by `pywebpush` |
| `VAPID_SUBJECT` | `mailto:your-email@example.com` | Valid contact URI for push services |
| `SMTP_*` *(optional)* | `smtp.gmail.com`, `587`, etc. | Optional caregiver missed-dose email escalation fallback |

### B. Frontend Service (`harbor-web`)

> **CRITICAL (`NEXT_PUBLIC_*` Build-Time Baking):** Next.js inlines `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_VAPID_PUBLIC_KEY` during `npm run build`, **not** at container boot. Deploy `harbor-api` first to get its exact `https://...onrender.com` URL, set both `NEXT_PUBLIC_*` env vars on `harbor-web`, and then trigger the `harbor-web` build (re-trigger a build with cleared cache whenever either variable changes).

- **Runtime:** Node `22.14.0` (pinned via `NODE_VERSION` in `render.yaml`)
- **Root Directory:** `frontend`
- **Build Command:** `npm ci && npm run build` (`package.json` already uses `next build --webpack`)
- **Start Command:** `npm start`

#### Required Frontend Environment Variables

| Variable | Example / Value | Notes |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | `https://harbor-api.onrender.com` | Exact backend HTTPS origin (no trailing slash) |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | `<same as VAPID_PUBLIC_KEY>` | Required at build time for browser push subscription |

### C. Deploy Order & CORS Synchronization

1. Deploy **Supabase** + run `alembic upgrade head` & `python -m app.seed.load`.
2. Deploy **`harbor-api`** on Render -> verify `GET https://<api>/healthz` returns `{"status":"ok","db":"ok"}`.
3. Create **`harbor-web`** on Render with `NEXT_PUBLIC_API_URL=https://<api>` and `NEXT_PUBLIC_VAPID_PUBLIC_KEY=<public key>` -> build and wait for live URL `https://<web>`.
4. Update **`harbor-api` `CORS_ORIGINS`** to `https://<web>` so browser preflight/fetch calls succeed.

---

## 5. External Tick Pinger Setup (`ISSUE-001`)

Free Render instances sleep after ~15 minutes of inactivity, so an in-process scheduler (`APScheduler`) would miss doses while asleep. Configure an external pinger (for example **cron-job.org**, GitHub Actions, or UptimeRobot HTTP monitor):

- **Method:** `POST`
- **URL:** `https://<api>/internal/tick`
- **Schedule:** Every `1` minute (`* * * * *`)
- **Header:** `X-Tick-Secret: <TICK_SECRET>`
- **Demo Simulation Note:** During presentations, append `?now=2026-11-23T22:15:00%2B06:00` to simulate mealtime windows and trigger missed-dose caregiver alerts immediately without waiting.

---

## 6. Post-Deploy Verification Checklist (Part B §3)

Once deployed with owner approval:
1. Check cold-start response time of `GET /healthz` and `POST /menu/suggest` (record real median/max & cold-start latency in `docs/AUDIT_REPORT.md`).
2. Sign in on `https://<web>/welcome` using `DEMO26` / PIN `1234`.
3. Verify `/menu`, `/stock`, `/bazar`, `/eval`, `/reminders`, and `/patient/[token]` end-to-end in a clean mobile browser.

