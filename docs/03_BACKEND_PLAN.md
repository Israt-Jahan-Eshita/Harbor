# 03 — Backend Plan (Python / FastAPI / PostgreSQL)

Algorithms, schemas, seed data and LLM contracts are in `docs/SPEC_FULL.md` (sections 6 to 11). This file is the step list. Each step has: goal, files, details, **done when**, tests. After each step update `docs/ENGINE_LOGIC_BN.md` for the module you touched.

Conventions:
- Pydantic v2 models for every request, response and LLM output.
- Errors: `{ "code": "SOME_CODE", "message": "...", "details": {} }` with correct HTTP status.
- All safety decisions return `{status, reasons[], trace[]}`.
- `core/` functions take plain data objects (dataclasses or Pydantic models), not DB sessions, so they are unit-testable without a database.
- IDs are UUIDs. Times are timezone-aware.

---

## B0 — Bootstrap
- **Goal:** runnable skeleton with PostgreSQL.
- **Files:** `docker-compose.yml` (PostgreSQL), `backend/app/main.py`, `config.py`, `db.py`, `.env.example`, `requirements.txt`, `/healthz`.
- **Details:** settings validated at startup; DB session dependency; `/healthz` checks DB connectivity; CORS from env; request-id middleware; JSON error handler. Look up and record the real package versions.
- **Done when:** `docker compose up` starts PostgreSQL, the API starts, `/healthz` returns ok, and a test hits it.

## B1 — Models and migrations
- **Goal:** all tables from SPEC section 6.
- **Files:** `models.py`, `alembic/`, first migration.
- **Details:** constraints (unique keys, enums as text with check constraints), indexes on `inventory_events(household_id, ingredient_id, created_at)`, `dose_schedule(due_at, status)`, `household_events(household_id, for_date)`.
- **Done when:** `alembic upgrade head` works on a clean DB and `downgrade` works; a test creates and reads each table.

## B2 — Seed data and loader
- **Goal:** the data the engine runs on.
- **Files:** `seed/*.json`, `seed/load.py`.
- **Details:** ingredients (about 50 to cover the recipes), aliases (Bangla, Banglish, English; include common spellings), drug class map, drug-food rules, diet presets, age profiles, reference prices, and about 40 recipes with Bangla names, steps, `split_step_bn`, `split_removes`, `taste_score`. Use only the rules in SPEC section 9. Every file carries the "Prototype data… Not clinically reviewed" header (as a `_meta` field). Loader is idempotent (upsert by key).
- **Check the data:** every recipe ingredient key exists; every ingredient has all attributes (potassium, purine, sodium, gi levels), season months, perishable days, unit, reference price; every recipe has at least a clear Bangla name. Write a seed-validation script and test.
- **Owner review:** the owner will review the Bangla recipe text and ingredient attribute levels. Log a question in `ISSUES.md` when you are unsure of a level. Do not invent clinical values to fill gaps; mark as `UNVERIFIED` data instead.
- **Done when:** loader fills the DB from empty; validation script passes; demo household scenario data exists.

## B3 — Safety engine (`core/rules.py`)
- **Goal:** `check_dish_safe(member, recipe, context)`.
- **Details:** exactly the order in SPEC 7.1: unverified checks, allergens, drug-food rules, presets and age profiles (with split logic), else safe. Collect all reasons. Return trace lines like `ALLERGEN prawn_shellfish matches ingredient chingri -> BLOCKED: PRAWN_ALLERGY`.
- **Tests:** every rule in SPEC 9.2 and 9.3, allergen tag matching, `UNVERIFIED` for unknown ingredient and unmapped medicine, medicine unconfirmed (`verified_by_caregiver=false`) is ignored for rules but never auto-activated, multiple reasons collected.
- **Done when:** unit tests green with no network and no DB.

## B4 — Shared-pot (`core/shared_pot.py`)
- **Goal:** `find_shared_pot_dishes`.
- **Details:** SPEC 7.2. Include guests as temporary people (allergies, restrictions from the event payload). Single split step must satisfy all splitting members. Return candidates and excluded with reasons.
- **Tests:** demo household expected result (SPEC 9.7), two members splitting at the same step, a member needing something the recipe cannot split, guest allergy, member away.
- **Done when:** tests green.

## B5 — Inventory and Bangla quantity (`core/inventory.py`, `core/bangla_qty.py`)
- **Goal:** stock from events; phrase normaliser.
- **Details:** stock = signed sum; expiry awareness from last PURCHASED date and `perishable_days`; `normalize_bangla_qty` table in SPEC 8.3 plus Bangla digit conversion, confidence value, "set to X percent of last stock" semantic as ADJUST delta computation.
- **Tests:** each phrase row, Bangla digits, unknown phrase returns low confidence, SPOILED and ADJUST math, stock never silently negative (clamp and flag).
- **Done when:** tests green.

## B6 — Prices and scoring (`core/prices.py`, `core/scoring.py`)
- **Goal:** `get_price_estimate`, `score_dishes`.
- **Details:** SPEC 7.3 and 7.6. Weights from config. Return component breakdown. Price priority: last purchase, reference table, AgriPriceBD cross-check note for the five commodities only if the data was actually loaded (otherwise skip the cross-check and say so).
- **Tests:** repeat penalty, expiry bonus, season bonus, weights override, price source order.
- **Done when:** tests green.

## B7 — Validator and templates (`core/validator.py`, `core/templates.py`)
- **Goal:** `validate_response(output, tool_log)` and fallback templates.
- **Details:** SPEC 8.5 rules 1 to 5. Templates in Bangla for menu cards and split instructions.
- **Tests:** unknown recipe id, unknown rule id, invented ingredient, dose patterns (digits plus `mg`, `মিগ্রা`, `মিলিগ্রাম`, `ডোজ`, `বাড়ান`, `কমান`, `বন্ধ করুন`), oversize text, valid output passes, prompt-injection-looking text inside an explanation is rejected if it adds ingredients or claims safety for an excluded dish.
- **Done when:** tests green.

## B8 — Reminders (`core/reminders.py`)
- **Goal:** dose schedule creation and state machine.
- **Details:** SPEC flow E. Due time offsets from config (after_food = meal + 20 min, before_food = meal - 30 min, with_food = meal). Grace 30 min. States: pending, taken, missed, escalated. Idempotent transitions driven by `now`.
- **Tests:** each transition, idempotent repeated ticks, `now` override, time zone handling, a dose confirmed late (after missed) records `taken_late` or equivalent and stops further alerts.
- **Done when:** tests green.

## B9 — Bazar (`core/bazar.py`)
- **Goal:** shortfall, substitutes, simplified monthly list.
- **Details:** SPEC 7.4 and 7.5. Substitution groups config table in the seed. Substitutes re-checked with `check_dish_safe`. Items flagged when swapped or dropped.
- **Tests:** shortfall math with reserved stock, substitute must stay safe, over-budget handling, out-of-season swap, prices labelled estimated.
- **Done when:** tests green.

## B10 — LLM layer (`llm/`)
- **Goal:** clients and the three LLM tasks, all untrusted.
- **Details:** `client.py` (Groq and Gemini wrappers, timeout 20 s, one retry, temperature 0 to 0.2, structured output if supported, Pydantic parse and one repair retry, logging to `llm_calls`). `extract_prescription.py`, `parse_events.py`, `explain.py` per SPEC 8. Prompts in `prompts.py`. **Verify the current API shape and model ids for Groq and Gemini before coding** (docs or a tiny live call) and note what you verified.
- **Tests:** contract tests with recorded or mocked responses: valid output, malformed JSON, missing fields, extra fields, timeouts, refusals. Plus a small number of live smoke tests that are skipped when keys are absent.
- **Done when:** every failure mode returns `None` and the caller uses the fallback path.

## B11 — MCP tools and agent (`mcp/server.py`, `llm/agent.py`)
- **Goal:** the tool layer and the bounded loop.
- **Details:** register the 13 tools from SPEC 11 with typed signatures and docstrings. Agent loop per SPEC 10: whitelist, max 6 calls, tool log, final output validated against the tool log, deterministic fallback pipeline on any failure. Write tools require a confirmation token. **Verify FastMCP's current API from the installed package**; use the in-process client if it works, otherwise call functions directly and keep the server runnable (log it in `ISSUES.md`).
- **Tests:** tool schemas generated, a fake LLM that tries a non-whitelisted tool, a fake LLM that returns an excluded recipe id (validator must reject), loop cap, fallback path.
- **Done when:** tests green and the MCP server starts.

## B12 — API: households and members
- Endpoints per SPEC 13: create household (returns access code), login (code + PIN), state, members CRUD. PIN hashing. Signed session. Patient token generation.
- **Tests:** auth required, wrong PIN, patient token can only access its own doses, validation errors.

## B13 — API: prescriptions and medicines
- Upload image, call extraction, return draft; confirm endpoint with per-row confirmation and drug class mapping (fuzzy suggestions, caregiver chooses; "not modelled" option with a stored note). Delete the image after extraction (do not persist). Consent flag required.
- **Tests:** unconfirmed rows never become active; unmapped drug leads to `UNVERIFIED` downstream; consent missing is rejected.

## B14 — API: events and stock
- `POST /events/parse` (text or audio, speech to text, parse, resolve aliases and quantities), `POST /events/confirm`, `GET /stock`.
- **Tests:** the sample sentence from SPEC 8.2 end to end with a mocked LLM; unresolved item stays unresolved; nothing written before confirm.

## B15 — API: menu
- `POST /menu/suggest`, `/menu/review`, `/menu/cooked`. Run the agent, validator, fallback. Response includes candidates with score breakdown, excluded list with reasons, explanation (or template), split instruction, missing ingredients.
- **Tests:** demo household result; Review with guests changes servings and menu; validator failure uses template; agent failure uses deterministic pipeline.

## B16 — API: bazar
- `/bazar/build`, `/bazar/confirm`, `/bazar/purchased` (writes PURCHASED events and price observations).

## B17 — API: reminders, push, dashboard, tick
- `/reminders/due`, `/reminders/{id}/taken`, `/dashboard/doses`, `/push/subscribe`, `/internal/tick` (secret header, optional admin `now` override). Push sending with generic text only; email fallback; in-app banner data.
- **Tests:** tick idempotency, escalation after grace, generic notification text (assert no condition or medicine name appears), polling endpoint.

## B18 — Evaluation harness and API
- `eval/cases.json` (30 hand-labelled cases: 10 allergy, 10 multi-condition, 10 drug-food), `baseline.py` (plain model prompt, no tools, 3 runs per case), `run_eval.py` (Harbor pipeline), metrics per SPEC 16.2, `results.md`, `GET /eval/results`.
- Labels are written by a human from the seed rules, not generated by running the engine.
- **Report only real numbers.**

## B19 — Engine explorer API
- `POST /engine/check` read-only: given member data and a recipe key, return the full rule trace. Used by the frontend `/engine` page for the presentation.

## B20 — Hardening
- Rate limits on LLM endpoints, input size limits, consistent errors, log hygiene, config validation, docs update, README with setup and env vars, final `ENGINE_LOGIC_BN.md` pass.

---

## API conventions
- JSON only (multipart for image/audio).
- Every list endpoint paginated or bounded.
- Every response that contains a safety decision includes `trace`.
- Bangla user-facing messages are returned as message keys plus parameters; the frontend translates, except LLM explanations and templates which are Bangla text.

## Backend definition of done
All B-steps complete, unit and integration tests green, LLM contract tests green, evaluation run produced real numbers, `ENGINE_LOGIC_BN.md` complete, `ISSUES.md` up to date.

