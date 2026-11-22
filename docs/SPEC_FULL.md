# HARBOR: Family Care Manager — Full Technical Spec

> Role of this file: the detailed technical spec (algorithms, schemas, seed data, LLM contracts, flows). Process rules, design system, testing and the Bangla engine explanation live in the other docs (`AGENT_PROMPT.md`, `docs/01` to `docs/06`, `docs/ENGINE_LOGIC_BN.md`, `docs/ISSUES.md`).
> If this file conflicts with those, the numbered docs win. Log the conflict in `docs/ISSUES.md` and ask the owner.

Audience: a coding agent (and the human owner) who must turn the idea into a working, deployed product.
Read this whole file before writing code. It defines the idea, the hard rules, the architecture, the data, the algorithms, every flow, the deployment, and the order of work.

---

## 0. Instructions to the coding agent

1. Build in the priority order of section 18. Get one end-to-end flow working and deployed before adding anything else.
2. Never break the guardrails in section 2. If a task seems to need breaking one, stop and ask the owner.
3. Do not invent clinical rules. The only drug-food, allergen and diet rules allowed are the seed rules in section 9. More can be added by the owner later.
4. Every LLM output is untrusted. Parse into a Pydantic model, validate, and fall back to a template on failure.
5. Keep the safety path pure Python with no network calls. It must run offline and be unit tested.
6. Write tests as you go (section 16). Do not mark a stage done with failing tests.
7. Keep the UI Bangla-first. Every user-facing string lives in a translation file.
8. Prefer boring, simple solutions. This is a hackathon prototype that must run reliably from a link.
9. Deadline pressure: the owner wants everything built within about a day. Nothing is cut unless the owner approves. If time is at risk, log it in `docs/ISSUES.md` and ask.

---

## 1. The idea in one page

**Product:** Harbor is a Bangla-first web app for households where one or more members live with chronic conditions (diabetes, high blood pressure, kidney disease, high uric acid, food allergies). One caregiver, usually the person who cooks, manages everyone.

**What it does:**
- Tells the caregiver what is safe to cook tonight for every person in the house.
- Shows which portion to set aside, and for whom, at which cooking step, so there is one pot instead of three or four separate dishes ("shared-pot cooking").
- Reminds patients to take medicines timed to real mealtimes, with one big button to confirm, and alerts the caregiver if a dose is not confirmed.
- Tracks household stock through voice or text in everyday Bangla, handles events like guests, and plans a monthly bazar list within a budget using estimated prices and seasonal items.

**The core design decision (the thing judges must understand):**
AI handles language and images only (speech, informal Bangla, prescription photos, short explanations). Whether a food is safe is decided by deterministic Python code over curated rule tables. The language model only ever sees dishes that already passed the safety checks, and a validator rejects any model output that is not grounded in tool results.

**Target users:**
- Primary: the household caregiver who cooks and manages medicines.
- Secondary: elderly patients who need one simple reminder button.
- Later version: relatives living abroad who want alerts.

**Problem it solves:**
- Chronic diseases cause about 71 percent of deaths in Bangladesh (WHO). The 2018 STEPS survey found hypertension in about 27 percent of adults and diabetes in about 9.8 percent.
- Households have several patients and one cook. Separate cooking is unrealistic, so restrictions slip.
- Medicines can clash with everyday foods (for example ACE inhibitors with high-potassium foods like spinach and coconut water; grapefruit with some statins).
- Elderly patients often take after-meal medicines alone, so a missed dose goes unnoticed.
- Pill reminder apps do not know what is being cooked, recipe apps do not know what was prescribed, and chatbots answer from memory and can forget an allergy. One confident wrong answer is worse than no answer.

---

## 2. Guardrails (non-negotiable)

1. **AI never decides safety.** Only `check_dish_safe` and related pure-Python code decide.
2. **Harbor never suggests, changes or stops a medicine, and never states a dose.** It only schedules reminders for medicines the caregiver confirmed from a prescription.
3. **Caregiver confirmation gate.** Nothing extracted from a prescription or from voice/text becomes active until the caregiver confirms it on screen.
4. **Fail safe.** Unknown ingredient or unmapped medicine gives `UNVERIFIED` and the dish is not suggested.
5. **Validator before display.** LLM text is shown only if it passes the validator; otherwise a fixed template built from the recipe record is shown.
6. **No model training. No GPU.** Off-the-shelf APIs only.
7. **No clinical claims.** Never say "clinically validated" or "pharmacist reviewed". Say "rules would be reviewed by a pharmacist or dietitian before real use".
8. **Lock screen and notifications never contain a disease name.** Generic text only: "ওষুধের সময় হয়েছে".
9. **Prices are estimates.** Label every price "আনুমানিক" (estimated). No scraping of market sites. No live price API exists.
10. **Consent before the first upload** of a prescription photo or voice recording to a third-party API. Do not store prescription images by default; keep only the confirmed extracted fields.

---

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS | Bangla-first PWA, service worker for push, high-contrast patient view |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | One API service |
| Tools layer | FastMCP | Exposes the deterministic tools; see section 11 |
| Scheduler | Tick endpoint plus idempotent jobs | See section 14 (free hosting sleeps) |
| Database | PostgreSQL | Supabase in production (use the pooler connection string). Local PostgreSQL (Docker) for development and tests. No SQLite anywhere. |
| Speech to text | Whisper large v3 via Groq (model id `whisper-large-v3`) | Typed input always available |
| Language model | Groq-hosted `openai/gpt-oss-120b` | Event parsing, explanation, agent loop. Model name from env |
| Vision | A Gemini vision-capable model | Prescription extraction. Model name from env |
| Fuzzy matching | rapidfuzz | Ingredient alias matching |
| Push | Web Push (VAPID, `pywebpush`) plus email fallback plus in-app polling | iOS needs the PWA installed for push, so polling is the safety net |
| Tests | pytest | Rule engine first |
| Hosting | Render for frontend and backend, Supabase for DB | See section 15 |

All model names live in environment variables, never hard-coded, so they can be swapped without touching the rule engine.

---

## 4. Repository layout

```
harbor/
  README.md
  HARBOR_BUILD_PLAN.md
  backend/
    requirements.txt
    alembic/
    app/
      main.py                 # FastAPI app, CORS, health
      config.py               # env settings
      db.py                   # engine, session
      models.py               # SQLAlchemy models
      schemas.py              # Pydantic request/response + LLM output schemas
      api/
        households.py  members.py  prescriptions.py  events.py
        menu.py  bazar.py  reminders.py  stock.py  eval.py  internal.py
      core/                   # PURE PYTHON, no network
        rules.py              # check_dish_safe, rule matching
        shared_pot.py         # find_shared_pot_dishes
        scoring.py            # score_dishes
        inventory.py          # stock from events, expiry
        bangla_qty.py         # normalize_bangla_qty
        bazar.py              # shortfall, substitutes, monthly list
        reminders.py          # dose schedule, state machine
        validator.py          # validate_response
        templates.py          # fallback Bangla templates
      llm/
        client.py             # Groq + Gemini clients, retries, timeouts
        prompts.py
        extract_prescription.py
        parse_events.py
        explain.py
        agent.py              # bounded tool-calling loop
      mcp/
        server.py             # FastMCP server wrapping core/ functions
      seed/
        ingredients.json  recipes.json  rules.json
        drug_class_map.json  aliases.json  prices.json  load.py
    tests/
  eval/
    cases.json  run_eval.py  baseline.py  results.md
  frontend/
    app/ (routes)  components/  lib/  messages/bn.json  messages/en.json
    public/ (manifest, service worker)
```

---

## 5. Architecture

```
 Caregiver (Next.js PWA)            Patient phone (/patient/[token])
   text / voice / photo / buttons       one big button, polling + push
              |                                   |
              v                                   v
 +----------------------------- FastAPI -----------------------------+
 |  api/*  (thin handlers, validation, auth by household code/token)  |
 |                                                                    |
 |  LLM layer (untrusted)           CORE (pure Python, trusted)       |
 |  - speech -> text                - check_dish_safe                 |
 |  - text -> event proposals       - find_shared_pot_dishes          |
 |  - photo -> draft medicines      - score_dishes                    |
 |  - agent: calls tools            - inventory, shortfall, bazar     |
 |  - explanation in Bangla         - reminders state machine         |
 |            |                     - validator                       |
 |            +----> MCP tools <--------+                             |
 +--------------------------------|-----------------------------------+
                                  v
                        Supabase Postgres
        (members, medicines, recipes, rules, inventory events, logs)

 External pinger -> POST /internal/tick  (runs due jobs, idempotent)
```

Responsibilities:
- **LLM layer:** turns messy input into structured proposals and turns validated results into Bangla text. It never writes to safety-relevant tables without caregiver confirmation.
- **Core:** all decisions. No network calls. Fully deterministic and unit tested.
- **MCP server:** thin FastMCP wrapper over core functions. The agent calls tools only through this layer so every fact is traceable.
- **Validator:** checks every LLM output against the tool-call log of the current request.

---

## 6. Data model (Postgres)

Use UUID primary keys. All timestamps are timezone-aware, display in Asia/Dhaka.

```
households(id, name, access_code, caregiver_pin_hash, consent_given bool,
           meal_times jsonb {"breakfast":"08:00","lunch":"13:30","dinner":"21:00"},
           monthly_budget_bdt int, created_at)

members(id, household_id, name, role text -- caregiver|patient|child|elder|other,
        age_group text -- child_under_1|child_under_5|child|adult|elder,
        conditions text[], allergies text[], diet_presets text[],
        patient_token text unique, notify_email text null, created_at)

prescriptions(id, member_id, raw_extraction jsonb, status text -- draft|confirmed,
              confirmed_at, created_at)           -- no image stored by default

medicines(id, member_id, prescription_id, name_as_written, generic_name,
          drug_class text, timing text -- before_food|after_food|with_food|any,
          meal_slots text[], verified_by_caregiver bool default false,
          active bool default true)

drug_class_map(drug_name unique, drug_class)       -- seed, see section 9
ingredient_aliases(alias, ingredient_id)           -- bn, banglish, en

ingredients(id, key unique, name_en, name_bn, category,
            allergen_tags text[], potassium_level, purine_level, sodium_level, gi_level,
            tags text[], season_months int[], perishable_days int,
            base_unit text -- g|ml|piece, ref_price_bdt numeric, ref_price_per numeric)

recipes(id, key unique, name_bn, name_en, servings_base int,
        ingredients jsonb [{"ingredient_key":..,"qty":..,"unit":..}],
        steps_bn text[], split_step_bn text null, split_removes text[] ,
        taste_score numeric 0..1, category text, est_cost_bdt numeric)

drug_food_rules(rule_id unique, drug_class, ingredient_attr, attr_value, severity,
                message_bn, message_en, source_note)
diet_presets(preset, attr, max_level)              -- see section 9

inventory_events(id, household_id, event_type -- PURCHASED|COOKED|SPOILED|RESERVED|ADJUST,
                 ingredient_id, qty_base numeric signed, source -- voice|text|ui|system,
                 raw_text, created_at)
household_events(id, household_id, kind -- GUESTS|GUESTS_CANCELLED|MEMBER_AWAY|OTHER,
                 for_date date, payload jsonb {"guest_count":4,"restrictions":["no_beef"]},
                 created_at)
price_observations(id, household_id null, ingredient_id, price_bdt, per_qty,
                   source -- user_purchase|reference_table|agripricebd, observed_at)
menu_suggestions(id, household_id, for_date, meal, payload jsonb,
                 validated bool, used_template bool, created_at)
bazar_lists(id, household_id, month text, budget_bdt, items jsonb, est_total_bdt,
            status -- draft|confirmed, created_at)
dose_schedule(id, medicine_id, due_at, window_end,
              status -- pending|taken|missed|escalated, confirmed_at)
alerts(id, household_id, member_id null, kind, channel, sent_at, payload jsonb)
llm_calls(id, task, model, input_summary, output jsonb, validated bool, latency_ms, created_at)
```

**Stock** of an ingredient = `SUM(qty_base)` over its inventory_events (PURCHASED positive; COOKED, SPOILED, negative; RESERVED negative until released; ADJUST signed). Events are append-only; corrections are new ADJUST events.

---

## 7. Core algorithms

### 7.1 `check_dish_safe(member, recipe, context) -> MemberResult`

Result status values: `SAFE_DIRECT`, `SAFE_WITH_SPLIT`, `BLOCKED`, `UNVERIFIED`. Each result carries `reasons: [rule_id, ...]` and a human-readable trace.

Evaluation order for one member and one recipe:
1. **Unverified checks.** If any recipe ingredient is missing from the ingredients table or lacks required attributes, return `UNVERIFIED: UNKNOWN_INGREDIENT`. If an active, confirmed medicine of the member has a name not in `drug_class_map`, return `UNVERIFIED: UNMAPPED_MEDICINE` (the confirm gate forces the caregiver to map it, see 8.1).
2. **Allergens.** If `member.allergies` intersects any ingredient's `allergen_tags`, return `BLOCKED: <ALLERGEN>_ALLERGY` (for example `PRAWN_ALLERGY`).
3. **Drug-food rules.** For each active confirmed medicine class, and each ingredient, if a row in `drug_food_rules` matches (class, attribute, value), return `BLOCKED: <rule_id>`.
4. **Diet presets and age profiles.** For each preset of the member, compare each ingredient's attribute level to the preset's max level.
   - If every violating ingredient is in `recipe.split_removes` (for example salt, green chilli) and the violated attribute is splittable (sodium only in the prototype), result is `SAFE_WITH_SPLIT`.
   - Otherwise `BLOCKED: <PRESET>_<ATTR>`.
5. If nothing triggered, `SAFE_DIRECT`.

Collect all reasons, not just the first, so the trace explains the block.

### 7.2 `find_shared_pot_dishes(household, date, meal, servings_context)`

1. Build the list of people eating: all present members plus guests from today's `household_events` (guests may carry temporary restrictions or allergies).
2. For every recipe in the database, run `check_dish_safe` for every person.
3. Household status for a recipe:
   - Any `BLOCKED` or `UNVERIFIED` gives status `EXCLUDED` (keep the reasons for the "why blocked" panel).
   - All `SAFE_DIRECT` gives `SAFE_DIRECT`.
   - Otherwise (some `SAFE_WITH_SPLIT`) gives `SAFE_WITH_SPLIT`, valid only if one single split step in the recipe handles every splitting member. Record `split_for: [member names]` and `split_step_bn`.
4. Return candidates and the excluded list with reasons.

Complexity is O(recipes x people), tiny. Run it on every request, no caching.

### 7.3 `score_dishes(candidates, household_state)`

```
Score = w1*stock_fit + w2*expiry_bonus + w3*season_bonus + w4*health_fit
      + w5*taste + w6*price_fit - w7*repeat_penalty
```
All components are normalised to 0..1. Default weights (tunable in config): `w1=0.25, w2=0.15, w3=0.10, w4=0.15, w5=0.10, w6=0.15, w7=0.30`.

- `stock_fit`: share of recipe ingredient quantity (scaled to servings) already in stock.
- `expiry_bonus`: ingredients in stock that have passed about 70 percent of their `perishable_days` since the last PURCHASED event raise the score.
- `season_bonus`: share of recipe ingredients in season this month.
- `health_fit`: 1.0 for `SAFE_DIRECT`, 0.7 for `SAFE_WITH_SPLIT`.
- `taste`: the curated `taste_score`.
- `price_fit`: `1 - min(1, shortfall_cost / per_meal_budget)`.
- `repeat_penalty`: 1 if the dish was cooked in the last 7 days (from COOKED events or past menu_suggestions), else 0.

Return the ranked list with the component breakdown (shown in the UI as "why this dish").

### 7.4 Bazar shortfall and substitutes

`calculate_bazar_shortfall(plan, stock, reserved)`: need (recipe qty x servings) minus current stock minus reserved quantity, floored at 0, per ingredient.

`find_safe_substitute(ingredient, household)`: look up same-category ingredients (config table of substitution groups), keep only candidates that keep every planned recipe `SAFE` for the household when swapped in (re-run `check_dish_safe`), prefer in-season, cheaper ones.

### 7.5 Monthly list

Inputs: budget, stock, members, season, estimated prices, past consumption.
1. Choose a set of dinner-type recipes for the month by repeated greedy picks: run `find_shared_pot_dishes` and `score_dishes`, apply a repeat penalty across the month, pick the top dish, simulate stock consumption, repeat (simplified: plan 7 distinct dinners and scale to the month; do not build full cost optimisation).
2. Sum the shortfall per ingredient across planned meals.
3. Price each item with `get_price_estimate`. If the total exceeds budget, replace the most expensive or out-of-season items with safe substitutes, then drop lowest-priority items and flag them.
4. Output items with qty, unit, estimated price, and a flag for "substitute used".
The caregiver reviews and edits; after shopping they log PURCHASED events (one tap "bought all" or per item).

### 7.6 Prices

`get_price_estimate(ingredient)` priority order:
1. The household's most recent PURCHASED price for that ingredient.
2. The `ref_price_bdt` from the seed reference table (compiled by the team from local market prices, labelled approximate).
3. For the five AgriPriceBD commodities (garlic, chickpea, green chilli, cucumber, sweet pumpkin) cross-check the reference table against that dataset's recent values and note disagreement above 30 percent.

Always return `{price, source, as_of}`. The UI shows "আনুমানিক".

---

## 8. LLM tasks (all untrusted, all validated)

Common rules for `llm/client.py`: timeout 20 s, one retry, temperature 0 to 0.2, use structured output / JSON mode if available, always parse with Pydantic and retry once with the error message, log every call in `llm_calls`. Any failure returns `None` and the caller uses the fallback path.

### 8.1 Prescription extraction (Gemini vision)

Input: the photo and a strict instruction to extract only what is visible and mark uncertainty.
Output schema:
```json
{
  "medicines": [
    {"name_as_written": "string", "generic_guess": "string|null",
     "timing": "before_food|after_food|with_food|any|unknown",
     "times_per_day": "int|null", "confidence": 0.0}
  ],
  "diet_notes": ["string"],
  "overall_confidence": 0.0
}
```
Rules:
- Never infer a medicine that is not written. Never output doses (ignore them).
- Store as `prescriptions.status = draft`.
- **Confirm screen:** a table of editable rows; low-confidence cells highlighted; caregiver ticks each row to confirm. Only confirmed rows become `medicines` with `verified_by_caregiver = true`.
- **Drug class mapping:** after confirmation, map the name through `drug_class_map` (fuzzy match with rapidfuzz, caregiver confirms the match). If there is no match, the caregiver must choose either a known class from a list or "not modelled (no food interaction in Harbor's rule table)". Show a short note that Harbor can only check the interactions it models.
- Do not persist the image. Delete it after extraction.

### 8.2 Event parsing (speech then Groq language model)

Pipeline: audio then `whisper-large-v3` then text, or typed text directly, then language model then event proposals.
Output schema:
```json
{
  "events": [
    {"type": "PURCHASED|COOKED|SPOILED|ADJUST|GUESTS|GUESTS_CANCELLED|MEMBER_AWAY",
     "item_raw": "string|null", "qty_phrase": "string|null",
     "guest_count": "int|null", "for_date": "ISO date|null",
     "guest_restrictions": ["string"]}
  ]
}
```
Rules:
- The model outputs raw phrases only. The backend resolves `item_raw` to an ingredient via `ingredient_aliases` and rapidfuzz (threshold about 85). It resolves `qty_phrase` with `normalize_bangla_qty`. The model never invents ingredient ids.
- Unresolved items are shown as "not recognised, pick one" in the confirm list.
- **Event confirm screen:** show proposals as chips (item, quantity, action). One tap "confirm all". Only then write inventory_events and household_events.
- Example input: `তেল প্রায় শেষ, অর্ধেকটা লাউ পচে গেছে, কাল ৪ জন মেহমান আসবে`
  Expected events: ADJUST oil to about 10 percent of last stock; SPOILED half of one bottle gourd; GUESTS count 4 for tomorrow.

### 8.3 `normalize_bangla_qty(phrase, ingredient) -> (qty_base, unit_base, confidence)`

Pure Python lookup, easy to extend. Approximate defaults (editable in a table):

| Phrase | Meaning |
|---|---|
| এক কেজি / ১ কেজি | 1000 g |
| আধা কেজি / আধ কেজি | 500 g |
| এক পোয়া | 250 g |
| আধা পোয়া | 125 g |
| এক মুঠো | about 50 g (leafy greens about 30 g) |
| দুই মুঠো | about 100 g |
| এক হালি | 4 pieces |
| এক ডজন | 12 pieces |
| এক কাপ | 240 ml |
| এক চামচ | about 15 ml (tablespoon) |
| অর্ধেকটা / আধখানা | 0.5 of the item (piece) |
| প্রায় শেষ | set stock to 10 percent of the last known stock |
| একটু আছে | set stock to 25 percent of the last known stock |
| শেষ / নেই | set stock to 0 |

Convert Bangla digits (০-৯) to ASCII before parsing. Return a confidence and flag low-confidence results for the confirm screen.

### 8.4 Explanation writer (Groq language model)

Input: only the top 3 validated dishes with their rule traces and split instructions, built from tool results. Nothing else.
Output schema:
```json
{"items":[{"recipe_id":"uuid","explanation_bn":"string","split_instruction_bn":"string|null",
           "rule_ids":["string"]}]}
```
Instructions: write 1 to 2 short Bangla sentences per dish, use only ingredients that appear in the recipe record, cite only the rule ids provided, never mention doses, never give medical advice.

### 8.5 Validator (`core/validator.py`, pure Python)

`validate_response(output, tool_log)` returns pass/fail with reasons. It checks:
1. Every `recipe_id` appears in the set returned by `find_shared_pot_dishes` during this request (from the tool-call log).
2. Every `rule_id` is in the set of rule ids attached to those dishes.
3. No ingredient name in the text that is not in the recipe's ingredient list (Bangla and English names from the table).
4. No dose patterns: digits followed by `mg`, `মিগ্রা`, `মিলিগ্রাম`, `ডোজ`, `বাড়ান`, `কমান`, `বন্ধ করুন`.
5. Schema valid, lengths bounded.
On failure, log it, and display the **fallback template** instead:
```
আজকের জন্য নিরাপদ: {name_bn}
{member_name}-এর অংশ {split_step_bn} আগে আলাদা করে তুলে রাখুন।
[Rule: {rule_id}]
```

---

## 9. Seed data (prototype, approximate, needs professional review before real use)

Mark every file with a header comment: "Prototype data compiled from general nutrition guidance and pharmacology references. Not clinically reviewed."

### 9.1 Drug classes (`drug_class_map.json`)

| Class | Example drugs |
|---|---|
| `ace_inhibitor` | enalapril, lisinopril, ramipril, perindopril, captopril |
| `arb` | losartan, telmisartan, valsartan, olmesartan, candesartan |
| `k_sparing_diuretic` | spironolactone, eplerenone, amiloride, triamterene |
| `statin_cyp3a4` | simvastatin, atorvastatin, lovastatin |
| `none_modelled` | explicit "no food interaction in Harbor's table" (the caregiver may choose this for other drugs) |

### 9.2 Drug-food rules (`rules.json`)

| rule_id | drug class | ingredient attribute | blocked when |
|---|---|---|---|
| `ACE_INHIBITOR_HIGH_POTASSIUM` | ace_inhibitor | potassium_level | high |
| `ARB_HIGH_POTASSIUM` | arb | potassium_level | high |
| `K_SPARING_DIURETIC_HIGH_POTASSIUM` | k_sparing_diuretic | potassium_level | high |
| `STATIN_GRAPEFRUIT` | statin_cyp3a4 | tag | `grapefruit_like` (grapefruit; treat pomelo/jambura the same, conservatively) |

### 9.3 Diet presets

| Preset | Attribute | Max allowed level | Split allowed |
|---|---|---|---|
| `low_gi` | gi_level | medium | no |
| `low_sodium` | sodium_level | medium (salt is high but splittable) | yes, for salt |
| `low_purine` | purine_level | medium | no |
| `low_potassium` | potassium_level | medium | no |

Age profiles (food filter only): `child_under_1` blocks tag `honey`; `child_under_5` blocks tag `whole_nuts`; `elder` has no extra rules in the prototype.

Staples (rice, roti) are out of scope: recipes describe the curry or side dish only.

### 9.4 Allergen tags
`prawn_shellfish`, `fish`, `egg`, `milk`, `peanut`, `tree_nut`, `wheat_gluten`, `soy`, `sesame`. A member allergy value matches the same tag.

### 9.5 Ingredient examples (levels are coarse: low / medium / high)

| key | name_bn | allergen_tags | potassium | purine | sodium | gi | notes |
|---|---|---|---|---|---|---|---|
| `palong_shak` | পালং শাক | - | high | medium | low | low | leafy |
| `daab_water` | ডাবের পানি | - | high | low | low | medium | |
| `banana` | কলা | - | high | low | low | medium | |
| `potato` | আলু | - | high | low | low | high | |
| `tomato` | টমেটো | - | medium | low | low | low | |
| `lau` | লাউ | - | low | low | low | low | bottle gourd |
| `jhinge` | ঝিঙে | - | low | low | low | low | ridge gourd |
| `kancha_pepe` | কাঁচা পেঁপে | - | low | low | low | low | |
| `chingri` | চিংড়ি | prawn_shellfish | medium | high | medium | low | |
| `rui_fish` | রুই মাছ | fish | medium | medium | low | low | |
| `egg` | ডিম | egg | low | low | low | low | |
| `masoor_dal` | মসুর ডাল | - | medium | medium | low | medium | |
| `salt` | লবণ | - | low | low | high | low | splittable |
| `green_chilli` | কাঁচা মরিচ | - | low | low | low | low | splittable (spice) |
| `onion`, `garlic`, `turmeric`, `oil` | পেঁয়াজ, রসুন, হলুদ, তেল | - | low | low | low | low | |
| `grapefruit` | জাম্বুরা (pomelo) | - | medium | low | low | low | tag `grapefruit_like` |

The agent must fill `season_months`, `perishable_days`, `base_unit`, `ref_price_bdt` for each ingredient. Reference prices are approximate and labelled so.

### 9.6 Recipes (target about 40, with a mix of dal, vegetable, fish, chicken, egg, mixed vegetable)

Each recipe: ingredient quantities for `servings_base`, Bangla steps, a `split_step_bn`, `split_removes`, `taste_score`.

Examples (write the others in the same shape):

```json
{
  "key": "lau_masoor_dal",
  "name_bn": "লাউ দিয়ে মসুর ডাল",
  "servings_base": 4,
  "ingredients": [
    {"ingredient_key":"lau","qty":300,"unit":"g"},
    {"ingredient_key":"masoor_dal","qty":120,"unit":"g"},
    {"ingredient_key":"onion","qty":50,"unit":"g"},
    {"ingredient_key":"garlic","qty":10,"unit":"g"},
    {"ingredient_key":"turmeric","qty":3,"unit":"g"},
    {"ingredient_key":"salt","qty":6,"unit":"g"},
    {"ingredient_key":"green_chilli","qty":10,"unit":"g"},
    {"ingredient_key":"oil","qty":20,"unit":"ml"}
  ],
  "split_step_bn": "লবণ ও কাঁচামরিচ দেওয়ার আগে",
  "split_removes": ["salt","green_chilli"],
  "taste_score": 0.8
}
```
Other starter recipes to include:
- `lau_chingri` (prawn with bottle gourd): blocked for prawn allergy.
- `palong_shak_bhaji` (spinach): blocked for ACE inhibitor, ARB, K-sparing diuretic and for `low_potassium` (high).
- `rui_macher_jhol` (fish curry with tomato): splittable at salt.
- `mishti_shobji` (bottle gourd, ridge gourd, raw papaya): passes for almost everyone, split at salt.
- `dim_bhuna` (egg): blocked for egg allergy.
- `murgir_jhol` (chicken curry): splittable at salt.

### 9.7 Demo household (also used in tests and the demo script)
- Father: chronic kidney disease, preset `low_potassium`.
- Mother: diabetes and hypertension, presets `low_gi` and `low_sodium`, confirmed medicine enalapril (class `ace_inhibitor`), after food.
- Child (age 8): prawn allergy.
- Caregiver: the mother's daughter-in-law or the household cook (role `caregiver`).
- Meal times: dinner 21:00.
Expected dinner result:
- `lau_chingri` EXCLUDED: `PRAWN_ALLERGY`.
- `palong_shak_bhaji` EXCLUDED: `ACE_INHIBITOR_HIGH_POTASSIUM` and `LOW_POTASSIUM_POTASSIUM`.
- `lau_masoor_dal`, `rui_macher_jhol`, `mishti_shobji`: `SAFE_WITH_SPLIT` (mother's portion set aside before salt and green chilli).

---

## 10. Planning agent (bounded)

Purpose: multi-step planning from a plain request such as "আজ কী রান্না করব?" or "কাল ৪ জন মেহমান", and for monthly planning. It decides which tools to call and in what order, then proposes a result.

Design:
- One function-calling loop in `llm/agent.py` using the Groq model.
- Tool whitelist (section 11) only. Tool schemas are generated from the core functions.
- Maximum 6 tool calls per request, then it must produce a final answer or the backend returns the deterministic pipeline result without LLM explanation.
- System prompt: "You plan meals. You must obtain every fact from tools. You cannot judge food safety. Return only recipe ids that tool results returned."
- The backend records every tool call and result in a per-request `tool_log`.
- Final output goes through the validator (8.5) using that `tool_log`.
- Reliability fallback: if the agent fails or returns invalid output, the backend runs the same pipeline directly (`find_shared_pot_dishes`, then `score_dishes`) and uses the template text. The user must never see a broken screen.

Where the agent loop is used: daily menu request, "Review" button recalculation after a guest event, and the monthly bazar plan.

---

## 11. MCP tool catalogue (`mcp/server.py`)

Implement each tool as a plain function in `core/` first, then register it in FastMCP with a typed signature and docstring. The agent calls the same functions through the MCP layer (use the FastMCP in-process client; if that causes friction under time pressure, call the functions directly but keep the MCP server runnable, and say so in the README).

| Tool | Input | Output |
|---|---|---|
| `get_household_state` | household_id, date | members, present people, meal time, budget, today's events |
| `get_inventory` | household_id | stock per ingredient, last purchase date |
| `update_inventory_event` | household_id, events[] | written event ids (only after caregiver confirmation) |
| `normalize_bangla_qty` | phrase, ingredient_key | qty_base, unit_base, confidence |
| `check_dish_safe` | member_id, recipe_id | status, reasons[] |
| `find_shared_pot_dishes` | household_id, date, meal | candidates (with split info), excluded (with reasons) |
| `score_dishes` | candidates, household_id | ranked list with component scores |
| `get_seasonal_items` | month | ingredient keys in season |
| `get_price_estimate` | ingredient_key, household_id | price, source, as_of |
| `calculate_bazar_shortfall` | plan, household_id | shortfall per ingredient |
| `find_safe_substitute` | ingredient_key, household_id, planned_recipe_ids | ranked substitutes |
| `build_monthly_list` | household_id, month, budget | items, estimated total, flags |
| `schedule_reminder` | medicine_id | dose_schedule rows |

`update_inventory_event` and `schedule_reminder` are write tools. The agent may only call them with ids that came from a caregiver-confirmed payload, enforced in the handler (reject if the confirmation token is missing).

---

## 12. End-to-end flows

### Flow A: Setup and prescription intake
1. Caregiver opens the app, enters household name, gets an access code and PIN. Consent screen: prescription photos and voice go to third-party APIs.
2. Add members (name, age group, role, conditions, allergies, preset). For a member with no prescription, pick a preset or an age profile. No medicine is involved.
3. For a patient with a prescription: upload photo, vision extraction produces a draft, the caregiver sees the editable table, ticks rows to confirm, maps unknown drug names, confirms. The image is deleted.
4. `schedule_reminder` creates dose rows tied to meal times for confirmed medicines.
5. Members who are patients get a personal link `/patient/{token}` for the big-button screen.

### Flow B: Event logging (voice or text, any time)
1. Caregiver types or holds a mic button and speaks in Bangla or Banglish.
2. Speech then text then event proposals (8.2), resolved by aliases and `normalize_bangla_qty`.
3. Confirm chips screen. On confirm, write inventory_events and household_events.
4. If an event affects today (guests, a member away, spoiled vegetables), flag today's menu as stale and show "Update menu".

### Flow C: Daily menu (the main demo flow)
1. Caregiver taps "আজ কী রান্না করব?".
2. Backend runs the agent (or the deterministic pipeline) to get candidates, then the ranked top 3.
3. For each person, `check_dish_safe` ran; excluded dishes keep their reasons in a collapsible "কেন বাদ?" panel (for example `BLOCKED: PRAWN_ALLERGY`).
4. Only the top 3 and their rule traces go to the explanation writer, then the validator. On failure the template is used.
5. The menu card shows: dish name, why it was chosen (score breakdown), the split instruction ("মায়ের অংশ লবণ ও কাঁচামরিচ দেওয়ার আগে আলাদা করে তুলে রাখুন"), missing ingredients, and a **Review** button.
6. **Review** opens a short form: guest count, guest food restrictions, anyone absent. Submitting writes a household_event and recalculates servings, menu, and shortfall.
7. After cooking, the caregiver taps "রান্না হয়েছে" which writes COOKED events for the used quantities and lets the repeat penalty apply from then on.

### Flow D: Monthly bazar
1. On the first day of each month (or when the caregiver taps "মাসের বাজার"), a notification asks the caregiver to check the pantry and enter a budget.
2. Caregiver updates stock via the pantry screen or voice, and enters the budget.
3. `build_monthly_list` produces items with quantities, estimated prices (labelled "আনুমানিক"), seasonal notes, and substitutes where an item was swapped for safety, season or budget.
4. Caregiver edits and confirms. After shopping they log purchases; stock and price observations update.
5. Scope note: this is the simplified version (section 7.5). Do not build full cost optimisation.

### Flow E: Medicine reminders and escalation
1. Each confirmed medicine has `timing` and `meal_slots`. Due time: `after_food` = meal time + 20 minutes; `before_food` = meal time - 30 minutes; `with_food` = meal time. Offsets are config values.
2. At the due time the patient gets a push (generic text, no disease name), and the patient screen shows one large Bangla button "খেয়েছি". The patient screen also polls `/reminders/due` every 15 seconds as a fallback.
3. Tapping the button marks the dose `taken` with the time.
4. If not confirmed by `due + grace` (default 30 minutes), the dose becomes `missed` and the caregiver is alerted (push, email, and a banner in the caregiver app). Status becomes `escalated`.
5. Roadmap, not in the demo: alerts to relatives abroad via SMS/WhatsApp.
6. The caregiver dashboard shows today's doses per patient (taken, pending, missed).

---

## 13. API surface (REST, JSON)

```
POST /households                      create, returns access_code
POST /households/login                code + PIN -> session token
GET  /households/{id}/state

POST /members                         PATCH/DELETE /members/{id}
POST /members/{id}/prescription       multipart image -> draft extraction
POST /prescriptions/{id}/confirm      confirmed rows + drug class mapping

POST /events/parse                    {text} or audio -> event proposals
POST /events/confirm                  proposals -> written events
GET  /stock

POST /menu/suggest                    {date, meal} -> top 3 + excluded + explanations
POST /menu/review                     guest/absence details -> recalculated menu
POST /menu/cooked                     recipe_id, servings -> COOKED events

POST /bazar/build                     {month, budget} -> draft list
POST /bazar/confirm                   and POST /bazar/purchased

GET  /reminders/due?token=...         patient polling
POST /reminders/{dose_id}/taken
GET  /dashboard/doses                 caregiver view

POST /push/subscribe                  save web push subscription

GET  /eval/results                    latest evaluation table
POST /internal/tick                   header X-Tick-Secret, runs due jobs
GET  /healthz
```
Authentication for the prototype: household access code + caregiver PIN gives a signed session token; patient links use an unguessable per-member token that can only read and confirm that member's doses. Note in the README that real auth is a production requirement.

---

## 14. Scheduling on free hosting

Free web services on Render sleep after a period of inactivity, so an in-process APScheduler will not fire while asleep. Use a **tick design**:
- `POST /internal/tick` (protected by `X-Tick-Secret`) runs all due work: create dose notifications whose time has come, mark overdue doses missed and alert, send the monthly bazar prompt on day 1, run the daily event check.
- Every job is idempotent and driven by database state (status flags and timestamps), so repeated or late ticks are harmless.
- An external pinger (any uptime-monitor or cron service that can call a URL every minute) hits `/internal/tick`. This also keeps the service warm.
- For the demo, add an admin-only `now` override (`?now=2026-11-25T21:00:00+06:00` on the tick endpoint) so reminders and escalation can be shown without waiting.
- APScheduler may still be used locally for convenience, but the deployed system must work from ticks alone.

---

## 15. Deployment (Render + Supabase)

**Supabase**
1. Create a project. Copy the **pooler** connection string (transaction or session pooler). If the direct connection fails from Render, the pooler is the fix.
2. SQLAlchemy URL form for psycopg v3: `postgresql+psycopg://USER:PASSWORD@HOST:PORT/postgres`.
3. Run Alembic migrations then `python -m app.seed.load` to load ingredients, aliases, recipes, rules, drug map, prices.
4. Free projects can pause after inactivity; open the dashboard before the demo.

**Render: backend (Web Service, Python)**
- Root directory `backend`. Build: `pip install -r requirements.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Health check path `/healthz`.
- Environment variables: `DATABASE_URL`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL` (default `openai/gpt-oss-120b`), `STT_MODEL` (default `whisper-large-v3`), `VISION_MODEL`, `CORS_ORIGINS` (the frontend URL), `SESSION_SECRET`, `TICK_SECRET`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `SMTP_*` (or an email API key), `TZ=Asia/Dhaka`.

**Render: frontend (Web Service, Node)**
- Root directory `frontend`. Build: `npm ci && npm run build`. Start: `npm start`.
- Environment variables: `NEXT_PUBLIC_API_URL` (backend URL), `NEXT_PUBLIC_VAPID_PUBLIC_KEY`.

**Common mistakes to avoid**
- CORS not set to the exact frontend origin.
- `NEXT_PUBLIC_*` variables must exist at build time, so rebuild after changing them.
- Free instances take tens of seconds to wake. Warm the service with a request before the demo, and let the pinger run.
- Service worker and push require HTTPS (Render provides it). On iPhone push needs the app installed to the home screen; keep the polling fallback.
- Never commit API keys.

---

## 16. Testing and evaluation

### 16.1 Unit tests (pytest, no network)
- Allergen block: prawn allergy blocks `lau_chingri`.
- Drug-food block: `ace_inhibitor` blocks `palong_shak_bhaji` with `ACE_INHIBITOR_HIGH_POTASSIUM`; `arb` and `k_sparing_diuretic` likewise.
- Statin and grapefruit-like tag.
- Presets: `low_potassium` blocks high-potassium dishes; `low_sodium` gives `SAFE_WITH_SPLIT` when only salt violates; blocked when a non-splittable ingredient violates.
- `UNVERIFIED` for an unknown ingredient and for an unmapped medicine.
- Shared pot: a household where two members need a split at the same step returns `SAFE_WITH_SPLIT` with `split_for` set; a household where one member needs a step the recipe cannot provide is excluded.
- Guest allergy from a household event excludes dishes.
- Scoring: repeat penalty lowers the score; expiry bonus raises it; weights come from config.
- `normalize_bangla_qty` over every row of the table, including Bangla digits.
- Stock from events with SPOILED and ADJUST.
- Validator: rejects an unknown recipe id, an unknown rule id, an invented ingredient, and dose-pattern text; accepts a clean output.
- Reminder state machine: pending, taken; pending to missed to escalated; idempotent tick.
- Demo household scenario (9.7) end to end.

### 16.2 Evaluation harness (`eval/`)
Goal: produce one real, measured result for the pitch.
- 30 labelled cases: 10 allergy, 10 multi-condition households, 10 drug-food conflict cases. Each case lists members, medicines, allergies, presets, and the **hand-labelled** set of recipe ids that must be excluded. Labels are written by a human from the seed rules, not generated by running the engine (avoid circularity).
- Baseline: a plain model prompt with the household description and the full recipe list, asking for 3 dinner suggestions, no tools, no validator. Run it 3 times per case because of variance.
- Harbor: the full pipeline.
- Metrics per system: unsafe dishes suggested (suggested id in the must-exclude set), missed allergens (a suggested dish that contains a member's allergen), share of suggestions carrying a rule citation.
- Output `eval/results.md` and serve it from `/eval/results` so it can be shown in the app.
- Report only what the run actually produces. Do not claim zero violations unless the run shows it.

---

## 17. Frontend screens (Bangla-first)

Use a Bangla web font (for example Noto Sans Bengali via `next/font`). Large touch targets. High contrast. All strings in `messages/bn.json` with an English fallback.

Caregiver app:
1. `/welcome` — create or enter household, consent.
2. `/members` — list, add, edit; per-member preset, allergies, medicines.
3. `/members/[id]/prescription` — upload, draft table, confirm gate, drug class mapping.
4. `/today` — main screen: "আজ কী রান্না করব?", top 3 cards with why, split instruction, rule badges, "কেন বাদ?" panel, **Review** button, "রান্না হয়েছে" button, today's dose dashboard.
5. `/log` — text box plus mic button, then the confirm-chips screen.
6. `/stock` — current stock, edit.
7. `/bazar` — monthly list, budget, "আনুমানিক" prices, substitutes marked, purchase tick-off.
8. `/eval` — evaluation results table.

Patient screen `/patient/[token]`:
- A full-screen card: patient name, one huge "খেয়েছি" button when a dose is due, otherwise "এখন কোনো ওষুধ নেই". No disease names anywhere. Polls every 15 seconds. Works as a PWA.

PWA: manifest, icons, service worker for push, offline shell for the patient screen.

---

## 18. Build order and what to cut first

Assume very limited time. Work strictly in this order. Deploy after P0 and again after each stage.

**P0 — The spine (must be deployed and working)**
1. Seed data (ingredients, about 15 recipes to start, rules, drug map) and DB models.
2. `core/rules.py`, `shared_pot.py`, `scoring.py` with unit tests green.
3. API: households, members, `/menu/suggest` (deterministic pipeline plus template text, no LLM yet).
4. Frontend: welcome, members (manual entry), `/today` with menu cards, rule badges, "কেন বাদ?" panel, split instruction.
5. Deploy to Render + Supabase. Demo household flow works from the link.

**P1 — The AI and the proof**
6. Explanation writer plus validator plus fallback.
7. Prescription extraction with the confirm gate.
8. Voice and text events: Whisper, parsing, aliases, `normalize_bangla_qty`, confirm chips, stock.
9. Reminders: dose schedule, patient big-button screen with polling, missed-dose escalation by tick, caregiver dashboard.
10. Evaluation harness with the 30 cases, results page.

**P2 — Completeness**
11. Planning agent loop with the MCP layer and tool log (before this, the deterministic pipeline stands in).
12. Review button with guest events and recalculation.
13. Simplified monthly bazar list with substitutes and prices.
14. Grow recipes to about 40. Web push plus email.

**P3 — Polish**
15. i18n cleanup, empty states, error toasts, demo seed button ("load demo household"), screen recording backup.

**Emergency cut list (ONLY with explicit owner approval; the owner wants nothing cut):**
1. Monthly bazar (keep only the shortfall for tomorrow's menu).
2. Web push (keep polling plus in-app banner).
3. Agent loop (keep the deterministic pipeline; keep the MCP server runnable and documented).
4. Recipes beyond about 20.
Never cut: rules and validator, caregiver confirmation gate, the demo household flow, the deployed link, the evaluation numbers.

---

## 19. Demo script (about 5 minutes)

1. Hook (20 s): one kitchen, three conditions, one cook.
2. Setup (40 s): load the demo household; show the prescription confirm gate on a sample image (nothing becomes active until confirmed).
3. Voice event (40 s): speak the Bangla sentence about oil, spoiled gourd, and four guests; show the confirm chips and the stock change.
4. Daily menu (90 s): tap "আজ কী রান্না করব?"; show prawn dish blocked with `PRAWN_ALLERGY`, spinach blocked with `ACE_INHIBITOR_HIGH_POTASSIUM`, the chosen dish with "মায়ের অংশ লবণ দেওয়ার আগে তুলে রাখুন". Tap Review and add guests.
5. Reminder (40 s): patient screen shows the big button, show a missed dose escalating to the caregiver (use the `now` override).
6. Proof (40 s): the evaluation page, plain model prompt versus Harbor, with real numbers.
7. Close (20 s): AI reads and explains, rules decide, validator checks.

Backups: recorded video of the full flow; seed button to reset the demo household; warm the service first.

---

## 20. Questions judges may ask, and the honest answers

- **Where is the AI central?** Without voice and prescription AI, data cannot get into the system, and the agent plans across stock, budget, members and events. Safety decisions are deliberately not AI.
- **Why not just ChatGPT?** It answers from memory and can drop an allergy. Harbor's decisions come from tools and rules, are traceable, and are checked by a validator.
- **Where do the rules come from?** Curated tables compiled from standard references. They are prototype data and would be reviewed by a pharmacist or dietitian before any real use.
- **What if the prescription reading is wrong?** The caregiver must confirm every field before anything is used.
- **What if the model hallucinates?** The validator rejects it and a fixed template is shown.
- **Why no training?** Not needed; the hard part is rules and data. Off-the-shelf models handle language and images.
- **Real prices?** No public live API exists. Estimates come from the household's last purchase and a reference table.
- **Does it recommend medicines?** Never. It schedules reminders for medicines the caregiver confirmed.

---

## 21. Definition of done (prototype)

- [ ] Deployed frontend and backend reachable from a link, connected to Supabase.
- [ ] Demo household produces the expected exclusions and splits (9.7).
- [ ] Rule engine unit tests pass, including `UNVERIFIED` and shared-pot cases.
- [ ] Prescription photo flow with confirm gate works on at least 3 sample images.
- [ ] Bangla voice and text events change stock after confirmation.
- [ ] Reminder with the big button works, and a missed dose alerts the caregiver.
- [ ] Validator rejects bad model output in a test and the template appears.
- [ ] Evaluation page shows real results from the 30 cases.
- [ ] README explains setup, env vars, the tick pinger, and the guardrails.

---

## 22. Glossary

- **Shared-pot (এক হাঁড়িতে রান্না):** cook one dish for everyone, setting aside an adapted portion at one step.
- **Split step (`split_step_bn`):** the point in the recipe before which a portion can be taken out (before salt, before green chilli, before the final tempering).
- **Caregiver:** the person who cooks and manages the household's food and medicines.
- **Bazar (বাজার):** grocery shopping.
- **daab (ডাব):** green coconut water. **palong shak (পালং শাক):** spinach. **jambura (জাম্বুরা):** pomelo (treated like grapefruit conservatively).
- **MCP:** Model Context Protocol; here, the tool layer the agent uses.
- **Tick:** a periodic call that runs all due jobs idempotently.

