# ISSUES — Harbor

Living log. **Newest issue at the top.** Never delete an issue; update its status and resolution.

## How to add an issue
1. Insert the new entry directly below the marker line `<!-- NEW ISSUES GO DIRECTLY BELOW THIS LINE -->` (so it is the first one).
2. Use the next number (higher than all existing ones).
3. Tell the owner in the chat at the same time. Do not wait.

## Severity
- **Blocker:** work cannot continue.
- **High:** breaks a guardrail, a core flow or the demo.
- **Medium:** wrong or missing behaviour with a workaround.
- **Low:** polish, wording, minor.
- **Question:** needs an owner decision.

## Status
`OPEN`, `WAITING_OWNER`, `IN_PROGRESS`, `RESOLVED`, `WONT_FIX` (owner decision only).

## Template
```
### ISSUE-NNN — <short title>
- Date:
- Severity:
- Status:
- Area: (backend / frontend / data / LLM / deploy / docs / testing)
- Found in: (step id, file, route)
- What happened:
- Expected:
- Reproduction / evidence: (exact commands and real output)
- What I tried:
- Suggested fix or options:
- Needs from owner:
- Resolution: (fill when resolved: what was done, commit, test that proves it)
```

---

<!-- NEW ISSUES GO DIRECTLY BELOW THIS LINE -->

### ISSUE-012 — Service Worker (`sw.js`) navigate catch block served cached `/` landing HTML on transient socket reset
- Date: 2026-11-23
- Severity: High
- Status: RESOLVED
- Area: frontend
- Found in: Phase 6 Playwright E2E (`frontend/public/sw.js`, `e2e/mobile-flows.spec.ts`)
- What happened: When `fetch(req)` inside `sw.js` experienced a transient keep-alive socket reset during rapid Playwright `page.goto("/stock")` or `page.goto("/reminders")`, the `.catch()` handler returned `caches.match("/")` (the precached `/` Landing Page HTML) as the response for `/stock` or `/reminders`, causing the wrong route component to render.
- Expected: `sw.js` retries `fetch(req.url)` once on transient socket error and falls back only to `caches.match(req)` for the exact requested URL.
- Reproduction / evidence: Observed `page.goto("/stock")` rendering `<h1>এক হাঁড়িতে সবার জন্য...</h1>` (`LandingPage`) and `page.goto("/reminders")` missing `a[href^="/patient/"]` in `mobile-flows.spec.ts`.
- Resolution: Updated `frontend/public/sw.js` to guard `only-if-cached`, retry `fetch(req.url)` once, and remove the cross-route `caches.match("/")` override.

### ISSUE-011 — Axe WCAG 2.1 A `label-content-name-mismatch`, `select-name`, and `scrollable-region-focusable` fixes
- Date: 2026-11-23
- Severity: Medium
- Status: RESOLVED
- Area: frontend
- Found in: Phase 6 `@axe-core/playwright` route audit (`components/layout/AppShell.tsx`, `app/patient/[token]/page.tsx`, `app/members/[id]/page.tsx`, `app/members/[id]/prescription/page.tsx`, `app/members/page.tsx`, `app/engine/page.tsx`, `app/log/page.tsx`, `app/eval/page.tsx`, `app/styleguide/page.tsx`)
- What happened: (1) `button[data-testid="lang-toggle"]` and `button[data-testid="patient-lang-toggle"]` had visible text `"বাং → EN"` while setting `aria-label="ভাষা"`, triggering WCAG 2.5.3 `label-content-name-mismatch` (`serious`); (2) raw `<select>`, `<textarea>`, and `<input type="file">` controls had sibling `<label>` tags without `htmlFor`/`id` association, triggering WCAG 4.1.2 `select-name` (`critical`); (3) horizontally scrollable `<pre>` / table blocks on `/eval`, `/engine`, and `/styleguide` lacked `tabIndex={0}`, triggering WCAG 2.1.1 `scrollable-region-focusable` (`serious`).
- Expected: Zero `serious` or `critical` Axe WCAG violations across all 17 routes in both Light and Dark themes (`34` route-theme scans).
- Reproduction / evidence: `AXE_VIOLATION [light] /: label-content-name-mismatch`, `AXE_VIOLATION [light] /members/[id]: select-name`, `AXE_VIOLATION [light] /eval: scrollable-region-focusable`.
- Resolution: Replaced overriding `aria-label` with `title` on both language toggle buttons, paired explicit `htmlFor`/`id` attributes on all `<select>`, `<textarea>`, and `<input type="file">` controls across all 5 form pages, and added `tabIndex={0}` to scrollable `<pre>` and table containers.

### ISSUE-010 — Evaluation provenance & Run 1 `max_tokens=500` reasoning truncation
- Date: 2026-11-23
- Severity: Medium
- Status: RESOLVED
- Area: docs / testing
- Found in: Phase 6 Audit Review (`eval/cases.json`, `eval/baseline.py`, `eval/run_eval.py`, `docs/ENGINE_LOGIC_BN.md`, `frontend/app/eval/page.tsx`)
- What happened: (1) `eval/cases.json` and docs referred to the 30 benchmark cases as "human-labelled", whereas they were authored by the coding agent from the seed rule table; (2) `eval/baseline.py` used `max_tokens=500`, which clipped `openai/gpt-oss-120b` internal reasoning tokens on 27 baseline calls (`400 json_validate_failed`) and hit the Groq 200k TPD `429` ceiling on `D10` runs 2-3.
- Expected: Honest attribution ("agent-authored, labelled from the seed rule table"), explicit by-construction caveat for Harbor's 0/30 score, preservation of Run 1 (`eval/results_run1.json`), and raised `max_tokens=2048` in `eval/baseline.py`.
- Reproduction / evidence: Probe on `openai/gpt-oss-120b` with `max_tokens=50` failed with `400 json_validate_failed` (`reasoning_tokens=47` needed even for `{"ok":true}`); `max_tokens=2048` succeeded (`completion_tokens=64`).
- Resolution: Preserved Run 1 in `eval/results_run1.json` & `eval/results_run1.md`, updated `eval/baseline.py` to `max_tokens=2048`, updated `eval/cases.json`, `eval/run_eval.py`, `frontend/app/eval/page.tsx`, `frontend/messages/{bn,en}.json`, `README.md`, `docs/ENGINE_LOGIC_BN.md`, and `docs/AUDIT_REPORT.md` with full methodology and baseline fairness caveats.

### ISSUE-009 — Gitignore policy decision on `docs/` and `eval/results.md`
- Date: 2026-11-23
- Severity: Question
- Status: RESOLVED
- Area: docs / deploy
- Found in: Phase 6 Audit Review (`.gitignore` vs `ISSUE-002`)
- What happened: Early owner instruction asked to ignore all `*.md` except `README.md` (currently enforced in `.gitignore` lines 2-6). However, `docs/02_ARCHITECTURE_AND_STACK.md` §4 and `ISSUE-002` reference `docs/` (`ENGINE_LOGIC_BN.md`, `AUDIT_REPORT.md`, `ISSUES.md`, `SEED_REVIEW.md`, `DEPLOY.md`) and `eval/results.md` as repository deliverables.
- Expected: Owner confirms which Markdown deliverables to track in Git before `git push`.
- Suggested fix or options:
  - **(Recommended) Option A:** Update `.gitignore` to track `docs/` and `eval/results.md` alongside `README.md` (while still ignoring `.env*`, scratch files, and root `AGENT_PROMPT.md` / `HARBOR_BUILD_PLAN.md`).
  - **Option B:** Keep current `.gitignore` (track only `README.md` and `eval/results.json`).
- Needs from owner: None.
- Resolution: Owner selected Option A on 2026-11-23. Updated `.gitignore` to track `docs/` and `eval/results.md` alongside `README.md` while keeping `.env*`, `AGENT_PROMPT.md`, and `HARBOR_BUILD_PLAN.md` untracked.

### ISSUE-008 — React hydration mismatch (#418) from SSR vs localStorage providers
- Date: 2026-11-23
- Severity: High
- Status: RESOLVED
- Area: frontend
- Found in: Phase 6 Playwright Mobile E2E (`frontend/lib/session.tsx`, `frontend/lib/i18n.tsx`, `frontend/lib/theme.tsx`)
- What happened: Reading `localStorage` during client initial render caused React minified error `#418` against SSR HTML during Next.js `next start` hydration.
- Expected: Zero React hydration warnings or errors across all 17 routes and `390x844` mobile browser navigation.
- Reproduction / evidence: Observed `Minified React error #418` in initial Playwright `390x844` run before provider fix.
- What I tried: Migrated `SessionProvider`, `I18nProvider`, and `ThemeProvider` to `useSyncExternalStore` with deterministic `getServerSnapshot` values and referentially cached snapshots.
- Suggested fix or options: None remaining; `httpOnly` cookie session recommended for multi-tenant production hardening beyond prototype scope.
- Needs from owner: None.
- Resolution: Rebuilt production bundle (`npm run build`), verified Vitest (`9/9`), ESLint (`0` errors), and Playwright `390x844` E2E (`1 passed (14.2s)`, `consoleErrors == []`).

### ISSUE-007 — Gemini 2.5 Flash unavailable on provided API key (404 NOT_FOUND)
- Date: 2026-11-22
- Severity: Medium
- Status: RESOLVED
- Area: LLM
- Found in: Step B10 pre-implementation verification (`VISION_MODEL`)
- What happened: Calling `gemini-2.5-flash` via `google-genai` returned `404 NOT_FOUND` ("This model models/gemini-2.5-flash is no longer available to new users"). Testing `gemini-3.8-flash` hit temporary `503 UNAVAILABLE`, while `gemini-3.5-flash` (from `gem.models.list()`) succeeded with JSON mode (`{"ok": true}`).
- Expected: Working Gemini vision-capable model configured in `VISION_MODEL`.
- Resolution: Updated default `VISION_MODEL` to `gemini-3.5-flash` in `backend/app/config.py`, `backend/.env.example`, and `backend/.env`.

### ISSUE-006 — Next.js 16.4.6 Turbopack panic on Windows PostCSS worker during next build
- Date: 2026-11-22
- Severity: Low
- Status: RESOLVED
- Area: frontend
- Found in: F0/F1 `npm run build` (`next build`)
- What happened: Default Turbopack `next build` on Windows threw `TurbopackInternalError: Failed to write app endpoint /page` while spawning the PostCSS transform child process for `app/globals.css`.
- Expected: `npm run build` produces an optimized production Next.js bundle cleanly.
- What I tried: Verified `next build --help` and ran `next build --webpack`, which compiles Tailwind v4 + `globals.css` reliably.
- Resolution: Set `"build": "next build --webpack"` in `frontend/package.json`.

### ISSUE-005 — Minor doc differences between HARBOR_BUILD_PLAN.md and docs/01..06
- Date: 2026-11-22
- Severity: Low
- Status: RESOLVED
- Area: docs
- Found in: Step 0 doc review (`HARBOR_BUILD_PLAN.md` vs `docs/01`–`06` and `docs/SPEC_FULL.md`)
- What happened: `HARBOR_BUILD_PLAN.md` mentions SQLite for local dev, `/today` route, and an automatic cut list, whereas `docs/01`–`06` specify PostgreSQL everywhere (no SQLite), the 16 canonical routes in `docs/04` (`/dashboard`, `/menu`, etc.), and zero scope cuts without explicit owner approval.
- Expected: Follow `AGENT_PROMPT.md` §2 rule: numbered docs (`docs/01` to `docs/06`) win over `SPEC_FULL.md` and `HARBOR_BUILD_PLAN.md`.
- Resolution: Resolved per `AGENT_PROMPT.md` §2 — using PostgreSQL everywhere, canonical routes from `docs/04_FRONTEND_PLAN.md` (with `/today` redirecting to `/menu` for convenience), and no scope cuts.

### ISSUE-004 — Seed data levels and Bangla recipe text need owner review
- Date: (planning)
- Severity: Question
- Status: OPEN
- Area: data
- Found in: B2 seed data
- What happened: Ingredient attribute levels (potassium, purine, sodium, GI) and Bangla recipe text are prototype data.
- Expected: Owner reviews the Bangla wording and the levels. Gaps are marked `UNVERIFIED`, not filled with guesses.
- Suggested fix or options: Agent produces the seed files, owner reviews them before the evaluation run.
- Needs from owner: Review time for the seed files; confirm any ingredient where the agent is unsure.
- Resolution:

### ISSUE-003 — Interpretation of "glass both mode"
- Date: (planning)
- Severity: Question
- Status: RESOLVED
- Area: frontend
- Found in: docs/04 section 1
- What happened: The style request was "neumorphism and skeuomorphism, also glass, both modes". The plan reads it as light and dark mode, with glass used for overlays and bars in both.
- Expected: Owner confirms or corrects.
- Suggested fix or options: (a) as planned; (b) add a separate visual style toggle (neumorphic vs glass) on top of light/dark.
- Needs from owner: Choose (a) or (b).
- Resolution: Owner confirmed Option (a) on 2026-11-22: Light and Dark modes (warm palette, no blue/purple/green), with Neumorphism + Skeuomorphism for cards/controls and Glassmorphism for bars/modals/overlays in both modes.

### ISSUE-002 — Keys, accounts and local database
- Date: (planning)
- Severity: Question
- Status: IN_PROGRESS
- Area: deploy
- Found in: Step 0
- What happened: The build needs Groq and Gemini keys, a Supabase pooler connection string, push (VAPID) keys, an email option, a git remote, and Docker for local PostgreSQL.
- Expected: Owner supplies or decides these at the start.
- Needs from owner: Provide or confirm each item. Without Docker, decide on a local PostgreSQL install or a separate Supabase dev project.
- Resolution: On 2026-11-22 owner confirmed: (1) Repository initialized at `D:\harbor` with `.gitignore` excluding all `*.md` except `README.md` and `docs/`; (2) Private GitHub remote `https://github.com/Israt-Jahan-Eshita/Harbor.git` configured as `origin` (not pushed yet); (3) Local Windows PostgreSQL 18 (`harbor_dev`, `harbor_test`) is live and verified; (4) `GROQ_API_KEY` (`openai/gpt-oss-120b`, `whisper-large-v3`) and `GEMINI_API_KEY` (`gemini-3.5-flash`) added and live-verified. Remaining items for Phase 5/7: VAPID push keys (can generate locally), optional SMTP credentials, and Supabase pooler URL before deploy.

### ISSUE-001 — Scheduler on free hosting
- Date: (planning)
- Severity: Medium
- Status: OPEN
- Area: deploy
- Found in: docs/02 section 7
- What happened: Free Render services sleep when idle, so scheduled work depends on an external pinger calling `/internal/tick`.
- Expected: Owner sets up a pinger (any service that can call a URL every minute) after deploy, or upgrades the instance.
- Suggested fix or options: Tick design with idempotent jobs and a demo `now` override (already planned).
- Needs from owner: Set up the pinger after deploy; confirm which service to use.
- Resolution:

