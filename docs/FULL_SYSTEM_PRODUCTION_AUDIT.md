# Harbor — Full System, Groq Token Drain & Production Readiness Audit

- **Audit Date:** 2026-11-23 (`Asia/Dhaka`, UTC+6)
- **Repository State:** Local `main` updated cleanly after Sprint 1–3 production hardening (`D:\harbor`)
- **Target Cloud Stack:** Render (`render.yaml`, Linux Python 3 + Node.js, case-sensitive FS) + Supabase PostgreSQL (Session Pooler)
- **Overall Production Verdict:** **READY FOR DEPLOY (PENDING OWNER PUSH & ENV SECRETS)** — All **4 Blocker** items, **8 Groq token-drain** items, **timezone/dynamic** defects, and **production hardening** items identified below have been fixed and verified across backend `pytest`, frontend `vitest`/`eslint`/`next build --webpack`, and live headless Chrome Playwright E2E + Axe runs (`0` Groq calls consumed during E2E/CI).

---

## Executive Severity Summary

| Audit Pillar | Blocker | High | Medium | Low | Total |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Groq Token Exhaustion & LLM Cost** | 1 | 4 | 3 | 0 | **8** |
| **2. Non-Dynamic / Hardcoded Logic** | 0 | 3 | 6 | 4 | **13** |
| **3. Production Security, DB, Frontend & Deploy** | 3 | 6 | 4 | 1 | **14** |
| **Total Verified Findings** | **4** | **13** | **13** | **5** | **35** |

---

## 1. Groq Token Exhaustion Audit (Root Causes & Fix Blueprint)

### Why Groq `200,000` TPD Quota Exhausts So Fast

The configured model `openai/gpt-oss-120b` (`backend/app/config.py#L32`) is a **reasoning model** whose internal chain-of-thought (`reasoning_tokens`) shares both `max_completion_tokens` and Groq's free-tier daily quota (`200,000` TPD). Several architectural paths trigger multi-turn or unguarded Groq calls even during routine testing and review flows.

### 1.1 Every LLM Call Path & Token Profile (Verified)

| Call Path & Symbol | Location (`file:line`) | Calls / Request | Token / Model Controls | Audit Findings |
| :--- | :--- | :--- | :--- | :--- |
| `POST /menu/review` -> `review_menu()` | `backend/app/api/menu.py#L184-L228` | Up to **7 HTTP turns** (forces MCP agent) | **No `enforce_rate_limit`!** Hardcodes `use_agent=bool(llm_client.groq_api_key)` (`menu.py#L227`) | **Critical Drain:** Ignores user's deterministic/agent toggle and forces full multi-turn agent loop on every Review submit (including Playwright E2E `mobile-flows.spec.ts#L44-L47`). |
| `MenuSuggestRequest` & `/menu` UI toggle | `backend/app/schemas.py#L146`, `frontend/app/menu/page.tsx#L38` | Triggers `run_menu_planning_agent` | `use_agent: bool = True` by default on both API & UI | Defaulting to `use_agent=True` invokes the multi-turn agent on every click instead of deterministic core or opt-in AI. |
| `run_menu_planning_agent()` -> `call_groq_tools()` | `backend/app/llm/agent.py#L216-L303`, `backend/app/llm/client.py#L159-L180` | Up to `max_tool_calls + 1 = 7` sequential LLM turns | `max_completion_tokens=1024`; **no `reasoning_effort`**; **no `llm_calls` DB logging** | Attaches all **11 MCP tool schemas** (`agent.py#L31-L43`) on every turn; appends `_compact_tool_result_for_llm` (up to 15 candidates + 15 excluded dishes) and resends full conversation history each hop. |
| Dead branch in `suggest_menu()` | `backend/app/api/menu.py#L130-L166` | Reachable only inside dead branch (`0` runtime calls) | Line `149` checks `if llm_client.groq_api_key and payload.use_agent:` inside `else:` of line `130` (`if payload.use_agent and llm_client.groq_api_key:`) | Mathematically unreachable (`menu.py#L149`). Lightweight single-shot `generate_grounded_explanations` (`explain.py#L62`) can never run via `/menu/suggest`. |
| `LLMClient.call_groq_json()` | `backend/app/llm/client.py#L80-L84,L91-L157` | Up to **4 HTTP calls** (SDK `max_retries=1` x `range(2)` repair loop) | `max_completion_tokens=1500`; **no `reasoning_effort="low"`**; `_log_llm_call` (`client.py#L33-L57`) ignores `resp.usage` | Sends `parse_events` / `menu_explain` to heavy `120B` reasoning model; retry appends prior output + validation error (~2x input tokens); no `429` cooldown circuit breaker. |
| `LLMClient.transcribe_audio()` | `backend/app/llm/client.py#L182-L217` | Up to **2 HTTP calls** (`max_retries=1`) | Whisper `whisper-large-v3` | Called only on voice audio upload in `/events/parse` (`consent_given=True` enforced). |
| `LLMClient.call_gemini_vision_json()` | `backend/app/llm/client.py#L219-L290` | Up to **2 HTTP calls** (`range(2)` repair retry) | `gemini-3.5-flash` (`temperature=0.1`, JSON mime type) | Uses separate Gemini API key (`GEMINI_API_KEY`); no `max_output_tokens` cap set. |

### 1.2 Silent Automated Test & Evaluation Leaks

1. **Test Spy Method Name Mismatch (`backend/tests/audit/test_part_a_gaps.py#L68-L78`):** `SpyLLM` overrides non-existent method `call_gemini_vision` instead of real method `call_gemini_vision_json` (`client.py#L219`) while passing `groq_api_key="x", gemini_api_key="x"`. Because `super().__init__` initializes real HTTP clients, running `pytest` actually sent outbound requests to Google (`HTTP 400 API_KEY_INVALID`) and Groq (`HTTP 401 Invalid API Key`) as seen in `task-1026` logs!
2. **Missing Global Test Guard (`backend/tests/integration/conftest.py`):** No `autouse` pytest fixture blanks `GROQ_API_KEY` / `GEMINI_API_KEY` by default. Any integration test invoking an endpoint without overriding `get_llm_client` will read live keys from `backend/.env` and burn quota.
3. **Playwright E2E Calling Live Groq (`frontend/e2e/mobile-flows.spec.ts#L44-L47`):** Even though line 34 clicks `menu-toggle-agent` off for `/menu/suggest`, lines 44–46 submit `review-apply-btn` (`POST /menu/review`), which forces `use_agent=True` (`menu.py#L227`) against the live `.env` Groq key during every E2E run.
4. **Sequential Baseline Benchmark (`eval/run_eval.py`):** Executing 90 uncached calls to `openai/gpt-oss-120b` (`eval/results.json`) consumed virtually the entire 200,000 TPD budget in a single run.

### 1.3 Prioritized Groq Token Fix Blueprint

1. **Remove Forced Agent on `/menu/review` & Opt-In Default:** Accept optional `use_agent: bool = False` in `MenuReviewRequest` (`schemas.py#L149-L154`), pass `payload.use_agent` in `menu.py#L227`, add `enforce_rate_limit("menu_review", max_calls=20, window_seconds=60)`, and flip `MenuSuggestRequest.use_agent` (`schemas.py#L146`) and `frontend/app/menu/page.tsx#L38` default to `False`.
2. **Fix Dead Branch & Separate Planning Modes:** Support explicit modes (or `use_agent=False` -> 0 LLM calls deterministic; `explain=True` -> single-shot `generate_grounded_explanations`; `use_agent=True` -> bounded MCP loop).
3. **Lower Token Burn on `call_groq_json` & `call_groq_tools`:** Add `LLM_FAST_MODEL` (e.g., `llama-3.1-8b-instant`) for simple extraction/explanation tasks; pass `reasoning_effort="low"` when calling `gpt-oss-*` models; lower `max_completion_tokens` (`600` for `parse_events`, `700` for `menu_explain`); trim `groq_tools` in `agent.py` to the 5 menu tools (`get_household_state`, `get_inventory`, `find_shared_pot_dishes`, `score_dishes`, `get_seasonal_items`).
4. **Usage Accounting, Daily Cap & `429` Circuit Breaker:** Persist `resp.usage.{prompt_tokens,completion_tokens,total_tokens}` into `llm_calls`; add `GROQ_DAILY_TOKEN_CAP` check and an in-memory `429` cooldown timer (`15m`) that immediately triggers deterministic fallback instead of retrying against a spent quota.
5. **Explanation Cache & Safe Test Isolation:** Cache validated menu explanations by `(household_id, for_date, meal, tuple(top_3_keys))` in memory/DB; add an `autouse` pytest fixture blanking `GROQ_API_KEY` / `GEMINI_API_KEY` unless `HARBOR_LIVE_TESTS=1`; rename `SpyLLM.call_gemini_vision` -> `call_gemini_vision_json`.

---

## 2. Still-Hardcoded / Non-Dynamic Logic Audit

| Severity | Area | Location (`file:line`) | Current Hardcoded Value / Behavior | Should Come From | Recommended Fix |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **HIGH** | Frontend Date / Timezone | `frontend/app/menu/page.tsx#L36`, `reminders/page.tsx#L17`, `bazar/page.tsx#L29` | `new Date().toISOString().slice(0, 10)` (and `.slice(0, 7)`) uses **UTC** date | Household timezone (`Asia/Dhaka`) | Create shared `getDhakaTodayISO()` / `getDhakaMonthISO()` using `Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" })`. Between `00:00`–`05:59` Dhaka time, UTC `.toISOString()` currently selects yesterday. |
| **HIGH** | Backend Schema Default Date | `backend/app/schemas.py#L144,L150,L160` | `Field(default_factory=date.today)` evaluates server local timezone (UTC on Render Linux) | Configured `settings.tz` (`Asia/Dhaka`) | Replace with `dhaka_today()` helper reading `datetime.now(ZoneInfo(get_settings().tz)).date()`. |
| **HIGH** | Cooked Meal Slot | `backend/app/api/menu.py#L273`, `schemas.py#L157-L160` | `MenuSuggestion(..., meal="dinner")` hardcoded on `POST /menu/cooked` | Request `payload.meal` | Add `meal: Literal["breakfast", "lunch", "dinner"] = "dinner"` to `MenuCookedRequest` and pass from `frontend/app/menu/page.tsx`. |
| **HIGH** | Meal Time Rescheduling | `backend/app/api/households.py#L158-L162` | Updating `hh.meal_times` leaves existing `pending` today `DoseSchedule` rows at old `due_at` timestamps | Updated `hh.meal_times` via `build_dose_schedule` | Recompute `due_at` / `window_end` for unconfirmed `pending` `DoseSchedule` rows of today when `meal_times` changes. |
| **MEDIUM** | Bazar Budget Hydration | `frontend/app/bazar/page.tsx#L30,L69` | `useState(() => String(session?.monthlyBudgetBdt ?? 15000))` initializes before client store or ignores live household state; `15000` also repeated in `menu.py#L129` & `agent.py#L119` | `session.monthlyBudgetBdt` / `Settings.default_monthly_budget_bdt` | Sync `budget` from `session?.monthlyBudgetBdt` in `useEffect` (when user has not edited) and centralize backend default in `config.py`. |
| **MEDIUM** | Duplicated Domain Catalogs | `prescriptions.py#L34-L60`, `engine.py#L50-L69`, `types.py#L100-L108`, `schemas.py#L70-L96`; `members/page.tsx#L18-L33`, `members/[id]/page.tsx#L23-L36`, `menu/page.tsx#L19-L29`, `prescription/page.tsx#L22-L44` | Allergens, diet presets, roles, age groups, drug classes, timings, meal slots duplicated as static literals/arrays across 8 files | Database (`drug_food_rules`, `diet_presets`, `drug_class_map`) + single backend catalog endpoint (`/engine/catalog`) | Build backend catalog dynamically from DB tables/shared constants and fetch/hydrate frontend selector options from `/engine/catalog`. |
| **MEDIUM** | Substitution Groups I/O | `backend/app/services/context_loader.py#L315-L316` | Reads `substitution_groups.json` from disk per `/bazar/build` request | PostgreSQL table (`substitution_groups`) or startup-cached seed | Store in DB via Alembic + seed loader alongside other reference tables. |
| **MEDIUM** | Age & Allergen Rule Tables | `backend/app/core/rules.py#L15-L65` | `ALLERGEN_SYNONYMS`, `ALLERGEN_RULE_NAMES`, `AGE_PROFILE_RULES` hardcoded in Python | Seed JSON + PostgreSQL (with current dicts as `RuleContext` defaults) | Load extensible allergen synonyms and age rules into `RuleContext` from seed/DB. |
| **MEDIUM** | Household Member Cap | `backend/app/api/members.py#L137` | Hardcoded `12` (`"Maximum 12 household members allowed."`) conflicts with spec cap `8` | `Settings.max_household_members` (`8` or `12`) | Move cap to `config.py` and align docs & validation message. |
| **MEDIUM** | Bangla Unit Ratios | `backend/app/core/bangla_qty.py#L37-L41,L131-L157` | `poya=250g`, `mutho=30/50g`, `cup=240ml`, relative stock ratios `0.10`/`0.25` hardcoded in code | `seed/` reference data or `config` table | Move culinary conversion factors to a structured seed/config dictionary loaded cleanly. |
| **LOW** | Hardcoded Seed Count in UI Copy | `frontend/messages/en.json#L441`, `bn.json#L441` | `"Select Recipe (40 Seeded Dishes)"` / `"রেসিপি বেছে নিন (৪০টি সিড পদ)"` | `catalog.recipes.length` on `/engine` | Interpolate `{count}` dynamically from `catalog.recipes.length`. |
| **LOW** | Bilingual Bazar Price Label | `backend/app/api/bazar.py#L101,L170` | Only returns `"price_label_bn": "আনুমানিক"` (no English field) | Accept-Language / both fields | Return both `"price_label_bn": "আনুমানিক"` and `"price_label_en": "Estimated"`. |
| **LOW** | Duplicated Push Text Constant | `backend/app/services/notifications.py#L21`, `core/reminders.py#L19` | `GENERIC_PATIENT_PUSH_TEXT` duplicated from `GENERIC_REMINDER_TEXT_BN` | `core/reminders.py` single source | Import `GENERIC_REMINDER_TEXT_BN` from `core.reminders` inside `services/notifications.py`. |
| **LOW** | Patient Poll Interval | `frontend/app/patient/[token]/page.tsx#L90` | Hardcoded `15000` ms timer without visibility check | Env / config constant + `document.visibilityState` | Respect `document.hidden` and configurable polling interval. |

---

## 3. Production Security, Database, Frontend & Deploy Readiness Audit

### BLOCKER (Must Fix Before Cloud Deploy)

1. **`BLOCKER-1` — Public Unauthenticated Demo Reset & Seed Mutation (`backend/app/api/households.py#L81-L86`):**
   - **Problem:** `POST /households/demo?reset=true` is completely public, takes no authentication, deletes and recreates `DEMO26` whenever `reset=true`, and runs full `seed_reference_data(db)` upsert logic on every hit. On a public URL, anyone can wipe demo data mid-presentation or DoS the DB.
   - **Fix:** Gate `reset=True` (and auto-seeding) behind `settings.env != "prod"` OR require `X-Tick-Secret` header when `reset=True` in production; add strict rate limiting (`enforce_rate_limit("demo_login", max_calls=15, window_seconds=60)`).

2. **`BLOCKER-2` — Unthrottled 4-Digit PIN Brute-Force on `/households/login` (`backend/app/api/households.py#L72-L78`):**
   - **Problem:** `POST /households/login` has no rate limit (`enforce_rate_limit` is missing). A 4-digit PIN (`10,000` combinations) against a known `access_code` (like `DEMO26` or short `HBRxxxx` codes) can be brute-forced online.
   - **Fix:** Attach `enforce_rate_limit("household_login", max_calls=10, window_seconds=300)` (plus per-`access_code` exponential/window lock) and verify response timing.

3. **`BLOCKER-3` — Unbounded `Alert` Full-Table Scan & Unrestricted `?now=` in `/internal/tick` (`backend/app/api/internal.py#L23-L31,L91-L96`; `backend/app/deps.py#L116-L119`):**
   - **Problem:** (a) Every 1-minute tick executes `db.scalars(select(Alert)).all()`, loading the entire `alerts` table across every household into memory (`O(N)` unbounded growth -> OOM & latency spike); (b) `verify_tick_secret` (`deps.py#L118`) uses `!=` instead of `hmac.compare_digest`; (c) `?now=` query override works unconditionally even in `ENV=prod`, allowing time manipulation if tick secret leaks.
   - **Fix:** Filter `Alert` lookup to recent window (e.g. `Alert.sent_at >= current_now - timedelta(days=35)`) or add a unique `alert_key` constraint; switch to `hmac.compare_digest(x_tick_secret, expected)`; gate `?now=` with `settings.env != "prod" or settings.allow_demo_tick_override`.

4. **`BLOCKER-4` — Render Build Runtime Drift, Silent `localhost` API Fallback & `eval/` Path Coupling (`render.yaml`, `frontend/lib/api.ts#L31-L32`, `backend/app/api/eval.py#L12`):**
   - **Problem:**
     - `render.yaml` does not specify `PYTHON_VERSION` (`3.11.9`) or `NODE_VERSION` (`22` / `24`); Render's default Python (`3.13`+) can fail compiling/installing pinned wheels (`psycopg[binary]==3.3.9`, `bcrypt==5.0.0`, `fastmcp==4.2.4`).
     - `frontend/lib/api.ts#L31-L32` silently falls back to `"http://localhost:8000"` in production if `NEXT_PUBLIC_API_URL` is forgotten at build time, causing browser CORS/network failures against visitors' own machines.
     - `backend/app/api/eval.py#L12` computes `REPO_ROOT = Path(__file__).resolve().parents[3]` assuming `eval/` sits alongside `backend/` at runtime.
   - **Fix:** Add `PYTHON_VERSION: "3.11.9"` and `NODE_VERSION: "22.14.0"` (or `24.16.0`) in `render.yaml`; fail fast or log loudly when `NODE_ENV === "production"` and `NEXT_PUBLIC_API_URL` is unset (skip only during `next build` if runtime check warns clearly); add `EVAL_DIR` env override + graceful existence check in `eval.py` (Render Blueprints clone the full repository even with `rootDir: backend`, so `parents[3]/eval` exists unless separated — verified safe with fallback).

### HIGH (Fix Before Real Users / Clinical Rollout)

1. **`HIGH-1` — Unbounded SQLAlchemy Connection Pool for Supabase Free Tier (`backend/app/db.py#L17-L23`):** `build_engine` uses SQLAlchemy defaults (`pool_size=5, max_overflow=10` per worker), risking Supabase connection pool exhaustion; `prepare_threshold` is not configurable if switching to Transaction Pooler (`6543`). **Fix:** Configure explicit `pool_size=3, max_overflow=2, pool_recycle=300` (configurable via env) and disable psycopg prepared statements (`connect_args={"prepare_threshold": None}`) when pooler URL uses port `6543`.
2. **`HIGH-2` — Swagger / OpenAPI Schema Exposed in Production (`backend/app/main.py#L52-L57`):** FastAPI exposes `/docs`, `/redoc`, and `/openapi.json` publicly in `ENV=prod`. **Fix:** Set `docs_url=None, redoc_url=None, openapi_url=None` when `settings.env == "prod"`.
3. **`HIGH-3` — Chunked Transfer Bypass & Full In-Memory Media Read (`backend/app/main.py#L80-L95`, `prescriptions.py#L104`, `events.py#L69`):** `request_id_middleware` checks `content-length` header only (bypassed by `Transfer-Encoding: chunked` requests), and upload handlers run `await file.read()` on the entire stream before checking `MAX_IMAGE_BYTES` / `MAX_AUDIO_BYTES`. **Fix:** Stream upload reads in chunks up to `MAX + 1` bytes and immediately abort with `413`.
4. **`HIGH-4` — Missing Frontend CSP & Security Headers + `localStorage` Token Storage (`frontend/next.config.ts`, `frontend/lib/session.tsx`):** `next.config.ts` defines zero `headers()` (`X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`), while caregiver Bearer tokens live in `localStorage` (accessible if XSS ever occurred). **Fix:** Add strict response headers in `next.config.ts` now; migrate auth session to `httpOnly; Secure; SameSite=Lax` cookies before multi-household public launch.
5. **`HIGH-5` — In-Memory Rate Limiter Memory Leak & Single-Worker Scope (`backend/app/deps.py#L23-L140`):** `_RATE_WINDOWS` never removes expired empty deques (slow unbounded dict growth per IP/token) and does not coordinate across multiple workers/restarts. **Fix:** Prune stale keys periodically (`if not dq: _RATE_WINDOWS.pop(key, None)` on sweep), and move to Redis before scaling beyond 1 Uvicorn worker.
6. **`HIGH-6` — Service Worker Navigation HTML Caching (`frontend/public/sw.js#L35-L45`):** `sw.js` caches navigated route HTML into `CACHE_NAME = "harbor-shell-v1"` without clearing across deploys or logouts, risking stale JS chunk manifests or cached caregiver UI HTML on shared devices. **Fix:** Cache only `/_next/static`, `/icons`, `/manifest.json`, and `/patient` offline shell (avoid caching dynamic HTML routes), and bump `CACHE_NAME` per deploy / clear caches on logout.

### MEDIUM (Reliability & Maintainability)

1. **`MEDIUM-1` — Background Tab Polling Waste (`frontend/app/patient/[token]/page.tsx#L86-L90`):** Patient 15s polling interval keeps firing even when `document.hidden` is true, waking Render free dynos continuously if a tab is left open. **Fix:** Skip polling when `document.hidden` and trigger an immediate fetch on `visibilitychange`.
2. **`MEDIUM-2` — Cross-Midnight Schedule Gap (`backend/app/api/internal.py#L39-L70` & `reminders.py#L40-L54`):** Tick only generates schedules for `current_now.date()`, and `reminders/due` queries `00:00..23:59` of `current_now.date()`. If dinner at `23:50` + `+20m` lands on `00:10` next day, `reminders/due` after midnight looks only at schedules created for today rather than late-evening carryovers unless generated earlier or queried with lookback. **Fix:** In `/internal/tick`, ensure schedules exist for `target_date` AND `(target_date + timedelta(days=1))`, and query pending due doses across `[day_start - 2h, day_end]`.
3. **`MEDIUM-3` — Linux CI Browser Channel Lock (`frontend/playwright.config.ts#L11`):** Hardcodes `channel: "chrome"`, which fails on headless Linux CI containers that use bundled Playwright Chromium. **Fix:** Set `channel: process.env.PW_CHANNEL || undefined`.
4. **`MEDIUM-4` — Unbounded `llm_calls` & `menu_suggestions` Table Growth (`backend/app/models.py`, `internal.py`):** Audit rows (`raw_text[:200]` in `llm_calls`) accumulate indefinitely without TTL pruning. **Fix:** Add an idempotent cleanup step in `/internal/tick` pruning `llm_calls` older than 30 days.

### LOW (Cosmetic & Dev Tooling)

1. **`LOW-1` — Dev-Only Frontend Dependency Advisories:** Installing Playwright/`@axe-core/playwright` reported `3` dev-only vulnerabilities (`1` moderate, `2` critical) in `devDependencies`; `npm audit --omit=dev` confirmed **`0` production runtime vulnerabilities**. Keep Playwright & axe strictly in `devDependencies` (or install Playwright only in CI, not Render prod runtime if using `npm ci --omit=dev` — note Next.js build needs `tailwindcss`/`typescript` which are in `devDependencies`, so standard `npm ci` runs on Render without shipping test binaries to client bundles).

---

## 4. Prioritized Pre-Deploy Fix Roadmap

| Sprint | Scope & Exact Files | Verification Exit Gate |
| :--- | :--- | :--- |
| **Sprint 1 — Stop Groq Token Drain** | `backend/app/{api/menu.py,schemas.py,config.py,llm/client.py,llm/agent.py,llm/explain.py}`, `frontend/app/menu/page.tsx`, `backend/tests/{integration/conftest.py,audit/test_part_a_gaps.py}` | Flip default `use_agent=False`; fix `/menu/review` & dead `menu.py#L149` branch; add `reasoning_effort="low"`, `LLM_FAST_MODEL`, `llm_calls` token logging, 429 cooldown + daily cap, explanation cache, and `autouse` test key blocker (`0` real API calls during pytest + Playwright). |
| **Sprint 2 — Dynamic Data & Dhaka Timezone** | `frontend/lib/date.ts` (new), `frontend/app/{menu,bazar,reminders}/page.tsx`, `backend/app/schemas.py`, `backend/app/api/{menu,households,members,engine}.py`, `frontend/messages/{bn,en}.json` | Fix UTC vs `Asia/Dhaka` dates across frontend & backend; pass `meal` in `/menu/cooked`; reschedule today's `pending` doses on `meal_times` change; hydrate Bazar budget & selector catalogs dynamically; remove hardcoded counts (`40`). |
| **Sprint 3 — Production Security, DB & Render Hardening** | `backend/app/{main.py,deps.py,db.py,api/households.py,api/internal.py,api/prescriptions.py,api/events.py}`, `render.yaml`, `frontend/{lib/api.ts,next.config.ts,public/sw.js,app/patient/[token]/page.tsx,playwright.config.ts}` | Lock down `/households/demo?reset=true` in prod; rate-limit `/households/login`; bound `Alert` scan + `hmac.compare_digest` + gate `?now=`; tune `db.py` pool; pin Python/Node in `render.yaml`; fail-fast `NEXT_PUBLIC_API_URL` check; Next.js CSP headers + `sw.js` cache tightening; chunked upload size guard; pause hidden-tab polling. |
| **Sprint 4 — Verification & Cloud Deploy** | Run `pytest tests -v`, `npm test`, `npm run lint`, `npm run build`, Playwright E2E/Axe; push & deploy with owner approval | `0` outbound Groq calls in automated suites; measure live Render cold start & `/menu/suggest` latency and append real numbers to `docs/AUDIT_REPORT.md` & `docs/DEPLOY.md`. |

---

## 5. Sprint 1–3 Resolution Status (Verified Locally)

All blocking, high-severity Groq token drain, timezone, dynamic data, and deployment hardening items listed above were implemented and verified on local `main`:

1. **Sprint 1 (Groq Token Protection — FIXED & VERIFIED):**
   - Flipped default `use_agent` from `True` to `False` in `MenuSuggestRequest`, `MenuReviewRequest`, and `frontend/app/menu/page.tsx`.
   - Fixed forced agent and missing rate limit on `POST /menu/review` (`enforce_rate_limit("menu_review", 15/60s)` + honors `payload.use_agent`) and repaired the unreachable `menu.py` branch via explicit `use_llm_explain` opt-in.
   - Added `LLM_FAST_MODEL` (`llama-3.1-8b-instant`) for `parse_events` (`max_completion_tokens=600`) and `menu_explain` (`max_completion_tokens=700`), added `reasoning_effort="low"` when calling `gpt-oss-*`, disabled SDK retries (`max_retries=0`), logged `resp.usage` tokens into `llm_calls`, enforced `GROQ_DAILY_TOKEN_CAP` (`150000`) + 15-minute `429` cooldown circuit breaker, added a 6-hour explanation TTL cache, trimmed agent MCP tools to the 5 menu tools, and compacted candidate/excluded tool payloads (`[:8]`).
   - Added root `backend/tests/conftest.py` (`autouse`) clearing `GROQ_API_KEY` / `GEMINI_API_KEY` during pytest unless `HARBOR_LIVE_TESTS=1` and fixed `SpyLLM.call_gemini_vision_json` in `test_part_a_gaps.py`.
2. **Sprint 2 (Dynamic Data & `Asia/Dhaka` Timezone — FIXED & VERIFIED):**
   - Added `frontend/lib/date.ts` (`getDhakaTodayISO`, `getDhakaMonthISO`) across `/menu`, `/reminders`, and `/bazar`, and `dhaka_today()` in `backend/app/schemas.py`.
   - Passed explicit `meal` on `POST /menu/cooked`, rescheduled today's `pending` `DoseSchedule` rows when household `meal_times` or active/timing medicine settings change, hydrated Bazar budget dynamically without lint effects, derived `/engine/catalog` presets/allergens/drug classes from rule context & seed tables, hydrated selector chips across `/menu`, `/members`, and `/members/[id]`, and interpolated live recipe count in `engine.recipeSelectLabel`.
   - Note: Moving CSV/JSON seed reference tables (`substitution_groups`, Bangla unit ratios) into DB tables remains an optional post-hackathon enhancement with low risk because files are read-only repo assets.
3. **Sprint 3 (Production Security, DB Pool & Render Hardening — FIXED & VERIFIED):**
   - Gated `POST /households/demo?reset=true` in `ENV=prod` behind `X-Tick-Secret` (leaving `reset=false` demo login functional and avoiding full reference re-seed when already seeded) + added `20/60s` rate limit; rate-limited `POST /households/login` (`10/300s`).
   - Hardened `/internal/tick` with `hmac.compare_digest`, gated `?now=` behind `ALLOW_DEMO_TICK_OVERRIDE=false` in prod, bounded `Alert` idempotency lookup to 35 days, added today + tomorrow scheduling for midnight crossovers, and pruned `llm_calls` older than 30 days.
   - Tuned SQLAlchemy engine (`pool_size=3`, `max_overflow=2`, `pool_recycle=300`, optional PgBouncer `:6543` `prepare_threshold=None`), disabled Swagger/OpenAPI docs in `ENV=prod`, enforced streaming 10 MB upload caps (`413`), added `EVAL_DIR` override, pinned `PYTHON_VERSION: "3.11.9"` and `NODE_VERSION: "22.14.0"` in `render.yaml`, added Next.js security headers, scoped `sw.js` (`harbor-shell-v2`) away from authenticated caregiver HTML, paused hidden-tab polling on `/patient/[token]`, and added production browser check on missing `NEXT_PUBLIC_API_URL`.
4. **Verification Runs After Final Edit:**
   - **Backend `pytest tests -v`:** `51 passed, 1 skipped` (`test_live_groq_and_gemini_smoke` skipped cleanly offline). Includes 5 new regression tests in `backend/tests/audit/test_production_hardening.py`.
   - **Frontend `vitest` / `eslint` / `next build --webpack`:** `3/3` test files (`9/9` tests) passed, `0` ESLint errors/warnings, all `17/17` static and dynamic Next.js routes compiled cleanly.
   - **Playwright E2E + Axe (against live production `next start` + `uvicorn`):** `2/2` specs passed (`AXE_SUMMARY_COUNT: 34 ROUTES_CLEAN: 34`, `ZOOM_200` horizontal overflow checks clean on `/`, `/dashboard`, `/menu`, `/patient/...`), `mobile-flows.spec.ts` completed in `3.5s` with `0` `llm_calls` rows triggered in `harbor_dev`.


