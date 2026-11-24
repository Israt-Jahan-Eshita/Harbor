# Harbor: Family Care Manager

**Harbor** is a bilingual (Bangla-first, full Bangla ↔ English conversion) Progressive Web App designed for multi-condition households managed by a single family caregiver. When family members manage overlapping dietary needs and medication schedules—such as chronic kidney disease, diabetes, hypertension, elevated uric acid, and food allergies—Harbor identifies shared-pot meals that everyone can safely eat or split at a single cooking step, plans whole-week (7 days × 3 meals) family menus with rolling variety and consolidated grocery shortfalls, tracks pantry inventory using Bangla units, manages monthly bazar budgets with AI-assisted item price & safety previews, coordinates clinician review approvals and fee payments, and delivers meal-timed medication reminders with strict patient privacy.

---

## Live Deployment & Demo Access

| Component | Live URL / Detail | Notes |
| :--- | :--- | :--- |
| **Live Frontend PWA** | **[https://harbor-web.onrender.com](https://harbor-web.onrender.com)** | Hosted on Render (`render.yaml`, Next.js `16.4.6` production build) |
| **Live Backend API** | **[https://harbor-api-9r22.onrender.com](https://harbor-api-9r22.onrender.com)** | FastAPI (`GET/HEAD /healthz`: [Health Check](https://harbor-api-9r22.onrender.com/healthz), [Swagger API Docs](https://harbor-api-9r22.onrender.com/docs)) |
| **Database** | **Supabase Managed PostgreSQL 18** | 21-table schema migrated via Alembic (`d4e7a82b1c03`) |
| **Demo Credentials** | Access Code: **`DEMO26`** · PIN: **`1234`** | Or click **"Load Demo Household"** on [`/welcome`](https://harbor-web.onrender.com/welcome) |
| **Auto-Deploy Blueprint** | [`render.yaml`](render.yaml) · [`docs/DEPLOY.md`](docs/DEPLOY.md) | Pushes to `main` automatically trigger Render API & Web rebuilds |

### Quick Judge Demo Links
- **Whole-Week Planner (7 Days × 3 Meals):** [https://harbor-web.onrender.com/menu](https://harbor-web.onrender.com/menu) *(switch to the **Whole Week (7 Days)** tab)*
- **Multi-Member Conflict Simulator & Rule Trace:** [https://harbor-web.onrender.com/engine](https://harbor-web.onrender.com/engine) *(switch to **Multi-Member Conflict Simulator**)*
- **30-Case Plain-LLM vs Harbor Safety Benchmark:** [https://harbor-web.onrender.com/eval](https://harbor-web.onrender.com/eval)
- **Monthly Bazar Checklist & Item Price/Safety Preview:** [https://harbor-web.onrender.com/bazar](https://harbor-web.onrender.com/bazar)
- **Clinician Approval & Consultation Fee Portal:** [https://harbor-web.onrender.com/reviews](https://harbor-web.onrender.com/reviews)
- **Medication Adherence & Disease-Free Patient Screen:** [https://harbor-web.onrender.com/reminders](https://harbor-web.onrender.com/reminders)

### Sample Demo Prescription (For Live OCR Testing)
To test live Gemini Vision prescription OCR, automatic dosage stripping (`mg`/`ml` removed), drug-class mapping (`ace_inhibitor`, `statin_cyp3a4`), and automatic meal-linked dose scheduling:
1. Download or select [`assets/demo_prescription.png`](assets/demo_prescription.png) from the repository.
2. Sign in (`DEMO26` / `1234`), open **Family Members (`/members`)** → **মা** → **Upload Prescription**, and upload `assets/demo_prescription.png`.
3. Verify the extracted draft rows (`Enalapril`, `Atorvastatin`, `Metformin`, `Pantoprazole`) appear with zero dose strengths saved and map cleanly into active schedules on confirmation.

> **Free-Tier Cold Start Note:** Both Render services run on the free tier (`render.yaml`). An initial request after idle sleep may take ~30–50 seconds to wake the container (monitored via `/healthz`).

---

## System Architecture

Harbor enforces a strict separation between natural-language parsing/explanation and safety-critical decision making: **AI reads and explains; deterministic Python code decides.**

![Harbor System Architecture](assets/architecture.svg)

### Architectural Layers

| Layer | Module Path | Responsibility | External Network / LLM Calls |
| :--- | :--- | :--- | :--- |
| **Client PWA** | `frontend/` | 20 App Router screens: caregiver workspace, whole-week planner, confirmation gates, patient reminder screen, clinician portal, conflict simulator, EN/BN switcher, warm Light/Dark UI | REST calls to FastAPI |
| **API & Tool Gateway** | `backend/app/api/`, `backend/app/mcp/` | Authenticated REST endpoints, signed `confirmation_token` verification, FastMCP 15-tool server | Request handling only |
| **Deterministic Core** | `backend/app/core/` | Dish safety checks, multi-member conflict precedence engine, shared-pot splitting, slot/date scoring, 7-day weekly planner (`weekly_plan.py`), Bangla unit normalization, inventory math, reminder FSM, validator, bazar planner | Strictly zero |
| **Bounded AI Layer** | `backend/app/llm/` | Prescription OCR (doses stripped), Bangla voice/text NLU event parsing, bounded 5-tool MCP planning agent (`<= 6` calls), grounded explanations, optional fast-model custom bazar pricing (`llama-3.1-8b-instant`), quota/cooldown circuit breakers | Groq & Gemini APIs |
| **Persistence & Alerts** | PostgreSQL 18, `services/` | 21-table relational schema via Alembic, audit logs (`llm_calls`), clinician review snapshots, persisted weekly plans, VAPID Web Push, SMTP notifications, `/internal/tick` | PostgreSQL, Web Push, SMTP |

---

## Hackathon & Sprint Feature Highlights

- **Whole-Week Household Meal Planner (`/menu` → Whole Week Tab):**
  - Plans **7 days × 3 meals (21 slots)** in one click (`POST /menu/week/plan`) using rolling repeat-avoidance, meal-slot affinity (`breakfast` / `lunch` / `dinner`), and deterministic date variety.
  - Per-day guest and away-member awareness, **meal-linked verified medicine reminder badges**, interactive **Safe Slot Swap & Lock** (`PATCH /menu/week/{plan_id}/slot` rejecting unsafe swaps with `400 UNSAFE_SLOT_SWAP` and overriding stale locks when new restrictions arise), virtual pantry depletion, consolidated 7-day BDT shortfall, and 1-click conversion into a draft bazar list (`POST /menu/week/{plan_id}/to-bazar`).
- **Same-Ingredient Multi-Member Conflict Steadiness (`/engine` → Conflict Simulator Tab):**
  - Hardened per-ingredient verdicts enforcing strict fail-closed precedence (`UNVERIFIED > BLOCKED > SAFE_WITH_SPLIT > SAFE_DIRECT`) and **proven order-invariance (`[A, B] == [B, A]`)**.
  - Classifies collisions across members (`UNVERIFIED_FAIL_CLOSED`, `SEVERITY_ESCALATION`, `MULTI_RULE_COLLISION`, `CONVERGENT_SPLIT`, `INCOMPATIBLE_SPLIT_BLOCKED`), recommends household-safe substitutes, and surfaces structured 2-pot recovery guidance on zero-safe-dish deadlocks.
- **Caregiver Workflow & Clinician Escalation (`/stock`, `/bazar`, `/reviews`, `/clinician/[token]`):**
  - **Quick Add to Pantry (`POST /stock/quick-add`):** Instant PostgreSQL stock updates from the verified nutrition catalog using zero AI tokens.
  - **Pre-Approval Bazar Checklist & Price/Safety Preview (`POST /bazar/predict-item`):** Review/uncheck generated items dynamically and preview cost, budget impact, and family allergy/safety warnings (with optional fast-model AI market estimation for custom items) before adding to the list.
  - **Clinician Review & Pre-Approval Fee Portal:** Token-gated clinical snapshot sharing (30-day conditions, allergies, medicines, adherence %, recent meals), clinician fee setting/waiver locking final approval (`400 PAYMENT_REQUIRED`), payment tracking (`bKash`/`Nagad`/`Card`/`Cash`), and auto-syncing approved diet presets back to the member's safety profile.

---

## Core Engineering & Safety Guardrails

1. **Zero AI Food-Safety Authority:** `backend/app/llm/` never computes or overrides safety verdicts. All dish eligibility and multi-member conflicts evaluate deterministically through `check_dish_safe`, `find_shared_pot_dishes`, and `evaluate_multi_member_conflict` in pure Python.
2. **Non-Prescriptive Medication Boundaries:** Harbor never recommends starting, stopping, or changing medications and never parses, stores, displays, or outputs medication dosages (`mg`/`ml` stripped automatically).
3. **Mandatory Caregiver Confirmation Gate:** Prescription extractions and parsed voice/text household events remain inert drafts until explicitly verified and submitted by the caregiver with a server-signed HMAC `confirmation_token`.
4. **Fail-Safe `UNVERIFIED` Handling:** Unmapped ingredients, unmapped drug classes, or unverified member medicines cause affected dishes to evaluate to `UNVERIFIED` and remain excluded from daily and weekly recommendations.
5. **Grounded Explanation Validator & Quota Resilience:** Every LLM-generated dish explanation passes deterministic lexical verification (`core/validator.py`) against actual engine outputs before reaching the UI. `LLMClient` enforces `max_retries=0`, a 15-minute `429` cooldown circuit breaker, a 150k daily token cap, and a 6-hour explanation cache with verified EN/BN template fallback.
6. **Prototype Clinical Scope Notice:** Reference seed data (`51` ingredients, `172` Bangla/English aliases, `40` Bangladeshi recipes, `5` drug classes, `4` drug-food rules, `4` diet presets) is compiled from general nutrition and pharmacology references and requires review by a qualified pharmacist or dietitian prior to clinical deployment.
7. **Privacy-Preserving Patient Mode & Notifications:** Lock-screen Web Push payloads and the `/patient/[token]` reminder screen display strictly generic prompts (`"ওষুধের সময় হয়েছে"` / `"Time for medicine"`) with zero disease names, condition tags, or medicine names.
8. **Approximate Pricing Disclosure:** All estimated ingredient and monthly/weekly bazar prices carry explicit `"আনুমানিক"` / `"Estimated"` markers unless backed by recent household purchase observations.
9. **Transient Media Handling & Consent:** Caregiver consent is verified (`consent_given`) prior to calling third-party AI APIs on prescription photos or voice recordings. Raw prescription images and audio bytes are processed strictly in memory and never persisted to disk or database columns.

---

## REST API Surface

All caregiver routes require `Authorization: Bearer <token>` obtained via `/households`, `/households/login`, or `/households/demo`. Error responses return structured JSON (`{ "code", "message", "details" }`).

| Domain | Endpoints | Purpose |
| :--- | :--- | :--- |
| **System** | `GET/HEAD /healthz`, `GET /drug-classes`, `GET /eval/results` | Database readiness & UptimeRobot probes, modelled drug-class catalog, measured benchmark access |
| **Households** | `POST /households`, `POST /households/login`, `POST /households/demo`, `GET /households/{id}/state`, `PATCH /households/{id}/settings` | Registration/login, demo household (`DEMO26`), consolidated state, meal times (auto-reschedules doses) & consent |
| **Members & Meds** | `GET/POST /members`, `GET/PATCH/DELETE /members/{id}`, `POST/PATCH/DELETE /members/{id}/medicines/{med_id}` | Member profiles (conditions, allergies, presets), verified medicines, daily dose scheduling |
| **Prescriptions** | `POST /members/{id}/prescription`, `POST /prescriptions/{id}/confirm` | Transient Gemini vision draft extraction (zero doses) and signed caregiver confirmation |
| **Events & Stock** | `POST /events/parse`, `POST /events/confirm`, `GET /stock`, `POST /stock/adjust`, `POST /stock/quick-add` | Voice/text Bangla event draft chips, ledger commits, non-negative stock calculation, manual adjustments & zero-token quick add |
| **Daily & Weekly Menu** | `POST /menu/suggest`, `POST /menu/review`, `POST /menu/cooked`, `POST /menu/week/plan`, `GET /menu/week/latest`, `PATCH /menu/week/{plan_id}/slot`, `POST /menu/week/{plan_id}/to-bazar` | Shared-pot top-3 ranking, guest/absence re-evaluation, cooked deductions, and 7-day (21-slot) planning with safe swap/lock & bazar export |
| **Bazar** | `POST /bazar/build`, `POST /bazar/confirm`, `POST /bazar/purchased`, `GET /bazar/latest`, `POST /bazar/predict-item` | Monthly ingredient aggregation, seasonality, safe substitutions, item price/budget/safety preview, purchase logging |
| **Clinician Reviews** | `GET/POST /clinician/reviews`, `POST /clinician/reviews/{review_id}/pay`, `GET /clinician/portal/{token}`, `POST /clinician/portal/{token}/fee`, `POST /clinician/portal/{token}/decision` | 30-day care-plan escalation, pre-approval fee setting/waiving, payment recording, formal approval & preset sync |
| **Reminders & Alerts** | `GET /reminders/due`, `POST /reminders/{dose_id}/taken`, `GET /dashboard/doses`, `POST /push/subscribe`, `POST /push/subscribe-patient`, `POST /internal/tick` | Token-scoped patient polling & confirmation, caregiver dose dashboard, push subscriptions, cron tick |
| **Engine Explorer** | `GET /engine/catalog`, `POST /engine/check`, `POST /engine/conflict-check` | Single-member deterministic rule trace and multi-member same-ingredient conflict & order-invariance inspection |

---

## Verified Technology Stack

| Component | Technology & Exact Versions |
| :--- | :--- |
| **Backend Runtime** | Python `3.11.9`, FastAPI `0.165.0`, Uvicorn `0.54.0`, Pydantic `2.14.4`, Pydantic Settings `2.16.3` |
| **Database & Migrations** | PostgreSQL `18` (`harbor_dev`, `harbor_test`, Supabase pooler in prod), SQLAlchemy `2.1.9`, Alembic `1.20.1`, Psycopg `3.3.9` |
| **MCP & Security** | FastMCP `4.2.4`, `bcrypt==5.0.0`, `itsdangerous==2.2.0`, `pywebpush==2.5.0`, `rapidfuzz==3.14.6` |
| **AI Providers (Transient / Bounded)** | Groq (`groq==1.7.0`: `openai/gpt-oss-120b`, `llama-3.1-8b-instant`, `whisper-large-v3`), Google Gemini (`google-genai==3.6.1`: `gemini-3.5-flash`) |
| **Frontend & UI** | Node.js `v24.16.0`, Next.js `16.4.6` (App Router), React `19.3.1`, Tailwind CSS `4.3.5`, TypeScript `5.9.3`, TanStack Query `5.108.2`, Lucide React `0.540.0` |
| **Testing Tooling** | Backend: `pytest==9.2.0`, `pytest-asyncio==1.5.0`, `httpx==0.28.1`; Frontend: `vitest==3.2.7`, `@testing-library/react==16.3.3` |

---

## Repository Layout

| Path | Description |
| :--- | :--- |
| `assets/architecture.svg` | 2D vector system architecture diagram |
| `assets/demo_prescription.png` | Sample synthetic prescription image for testing live OCR intake and automatic dose stripping |
| `backend/app/core/` | Pure-Python deterministic rules, multi-member conflict resolver, shared-pot & 7-day weekly planner, scoring, Bangla qty normalizer, inventory, validator, templates, reminders, bazar |
| `backend/app/llm/` | Groq & Gemini clients with quota/cooldown circuit breakers, Pydantic extraction prompts, bounded MCP agent, grounded explanation generator |
| `backend/app/mcp/` | FastMCP 15-tool server enforcing read/write separation and `confirmation_token` checks |
| `backend/app/api/` | FastAPI HTTP routers (`menu`, `engine`, `bazar`, `stock`, `clinician`, `prescriptions`, `events`, `reminders`, `households`, `members`) and Pydantic schemas (`schemas.py`) |
| `backend/app/seed/` | Prototype dataset (`51` ingredients, `40` recipes, `DEMO26`), validation script, idempotent DB loader |
| `backend/alembic/` | Database schema migration scripts (`21` tables) |
| `backend/tests/` | Unit, scenario, mocked LLM contract, conflict/weekly integration, and audit tests (`test_core_purity.py` verified) |
| `frontend/app/` | 20 Next.js App Router pages, global styles, and warm Neu/Skeu/Glass Light/Dark tokens |
| `frontend/components/` | Reusable accessible UI primitives and `AppShell` navigation |
| `frontend/lib/` | Typed API client (`api.ts`), bilingual i18n provider (`i18n.tsx`), theme & session contexts, WCAG contrast audit helper |
| `frontend/messages/` | Synchronized Bangla (`bn.json`) and English (`en.json`) translation catalogs |

---

## Local Development Setup

### 1. Prerequisites
- Python `3.11+`
- Node.js `20+`
- PostgreSQL `18` running locally (or via `docker compose up -d db`) with databases `harbor_dev` and `harbor_test`

### 2. Backend Setup

```powershell
cd backend
Copy-Item .env.example .env
# Populate DATABASE_URL, TEST_DATABASE_URL, SESSION_SECRET, TICK_SECRET, GROQ_API_KEY, GEMINI_API_KEY

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

alembic upgrade head
python -m app.seed.load
uvicorn app.main:app --reload
```

### 3. Frontend Setup

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Use `/welcome` to create a household or sign in with the seeded demo credentials (Access Code: `DEMO26`, Caregiver PIN: `1234`).

---

## Verification Commands

### Backend

```powershell
cd backend
# Pure deterministic + mocked contract + PostgreSQL integration suite
pytest -q

# Include live Groq & Gemini smoke verification (requires API keys in backend/.env)
$env:HARBOR_LIVE_TESTS = '1'
pytest -v
```

> **Windows IPv6 / Localhost Note:** Windows commonly resolves `localhost` to IPv6 `::1`. When running browser E2E checks against `http://localhost:3000`, launch the API with dual-stack/IPv6 binding or connect explicitly over `127.0.0.1`.

### Frontend

```powershell
cd frontend
npm test
npm run lint
npm run build
npx playwright test --reporter=list
```

> **Windows Build Note:** `package.json` configures `"build": "next build --webpack"` for reliable Next.js `16.4.6` production compilation on Windows.

---

## Evaluation Methodology & Caveats

The 30-case safety benchmark (`eval/cases.json`, `eval/baseline.py`, `eval/run_eval.py`) compares plain `openai/gpt-oss-120b` JSON prompting (3 runs per case, no deterministic rules or MCP tools) against Harbor's deterministic core (`check_dish_safe`, `find_shared_pot_dishes`, and template grounding).

1. **Label Provenance:** The 30 benchmark cases (`10` allergy, `10` multi-condition/age, `10` drug-food/fail-safe) were authored by the coding agent and labelled directly from the seed rule table (`backend/app/seed/{ingredients,rules,diet_presets}.json`), not by an external human clinician.
2. **By-Construction Determinism:** Because the benchmark ground-truth labels and Harbor's rule engine derive from the same seed rule table, Harbor's `0.0% (0/30)` unsafe recommendation rate holds by construction and verifies deterministic implementation fidelity rather than external clinical sensitivity.
3. **Baseline Run Caveats:** In Run 1 (`eval/results.json`, `max_tokens=500`), the plain model achieved `0.0% (0/30)` unsafe recommendations on the 10 allergy cases (`A01`-`A10`), `3.3% (1/30)` on multi-condition (`M07`), and `6.7% (2/30)` on drug-food (`D05`, `D06`), while `27/90` baseline calls failed (`70.0%` valid JSON) because `max_tokens=500` truncated `openai/gpt-oss-120b` internal reasoning tokens (`json_validate_failed`) and the final case (`D10` runs 2-3) hit Groq's 200,000 TPD free-tier rate limit (`HTTP 429`). A subsequent re-run attempt (`eval/results_run2_INVALID.json`) hit HTTP `429` on `26/30` cases and is excluded as invalid.

---

## Differences from the Submitted Proposal

Every architectural or operational adjustment between the initial proposal / build plan (`HARBOR_BUILD_PLAN.md`) and the built codebase is documented below and verified against the source tree:

| Proposal / Initial Plan Item | Built Implementation | Code Location & Rationale |
| :--- | :--- | :--- |
| **Local SQLite option** ("Local dev may use SQLite") | **PostgreSQL everywhere** (`harbor_dev`, `harbor_test`, Supabase pooler in prod); SQLite connection strings are explicitly rejected at startup | `backend/app/config.py` (`validate_postgres_url`), `backend/app/models.py` (uses PostgreSQL `ARRAY`, `JSONB`, `UUID`) |
| **In-process APScheduler** ("APScheduler may still be used locally") | **Idempotent HTTP Tick endpoint only** (`POST /internal/tick` with `X-Tick-Secret` header and `?now=` override); zero in-process background scheduler threads | `backend/app/api/internal.py`, `backend/app/core/reminders.py` (`evaluate_tick`) — ensures identical behavior on sleeping free-tier Render instances |
| **Gemini 2.5 Flash vision model** | **Default `VISION_MODEL=gemini-3.5-flash`** (configurable via env) | `backend/app/config.py` — `gemini-2.5-flash` returned HTTP `404 NOT_FOUND` for new API accounts (`ISSUE-007`) |
| **Single-language Bangla UI** | **Full bilingual `বাংলা ↔ English` UI & data conversion** across all 20 pages, rule traces, fallback templates, and unit labels | `frontend/lib/i18n.tsx`, `frontend/messages/{bn,en}.json`, `backend/app/core/templates.py` |
| **Next.js default `next build` (Turbopack)** | **`next build --webpack`** configured in `frontend/package.json` | `frontend/package.json` — avoids Windows Turbopack PostCSS child-process crash (`ISSUE-006`) |
| **`/today` daily menu route** | **Canonical route `/menu`** (Daily + Whole-Week tabs) with `/today` redirecting cleanly to `/menu` | `frontend/app/menu/page.tsx`, `frontend/app/today/page.tsx` (`router.replace("/menu")`, `ISSUE-005`) |
| **18 database tables** | **21 database tables** (added `push_subscriptions`, `clinician_reviews`, and `weekly_plans`) | `backend/app/models.py`, `backend/alembic/versions/` |

---

## Disclaimer

Harbor is an engineering prototype built to demonstrate deterministic multi-constraint family meal planning, grounded LLM output validation, and caregiver-in-the-loop safety gating. Seed nutrition, allergen, and drug-food rules have **not** undergone clinical pharmacist or dietitian review and must not be used for medical decision making without qualified clinical validation.
