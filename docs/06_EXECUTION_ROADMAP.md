# 06 — Execution Roadmap

Order of work, checkpoints, and when to ask the owner. Nothing in scope is cut. If time is at risk, log it in `docs/ISSUES.md`, tell the owner, and let the owner decide.

Effort labels: S (small), M (medium), L (large). They are relative, not hours. The owner wants the whole product within about a day, so work in vertical slices, keep each step tight, and do not gold-plate. Backend and frontend steps are defined in `docs/03_BACKEND_PLAN.md` (B-steps) and `docs/04_FRONTEND_PLAN.md` (F-steps).

---

## Phase 0 — Orientation and decisions (S)
1. Step 0 from `AGENT_PROMPT.md`: inspect repo and environment, read all docs, summarise understanding in 10 lines.
2. Ask the owner for: Groq key, Gemini key, Supabase pooler connection string, git remote decision, Docker availability, push keys (VAPID) or permission to generate them, email provider choice.
3. Resolve the open questions already in `docs/ISSUES.md`.
4. Look up and record current stable versions of all major libraries.

**Checkpoint P0:** owner confirms understanding and supplies what is needed.

## Phase 1 — Engine foundation (L)
B0 bootstrap, B1 models and migrations, B2 seed data, B3 safety engine, B4 shared pot, B5 inventory and quantities, B6 prices and scoring, B7 validator and templates, B8 reminders, B9 bazar.
- Unit tests green for every step.
- Update `ENGINE_LOGIC_BN.md` after each.

**Checkpoint P1:** demo household scenario test passes (expected exclusions and splits from SPEC 9.7). Show the owner the trace output.

## Phase 2 — Frontend foundation (M) — can interleave with Phase 1
F0 bootstrap, F1 design system with `/styleguide`, F2 layout shell, navigation and i18n, F3 welcome and settings.

**Checkpoint P2:** `/styleguide` shows every component in light and dark mode with contrast results. **Owner reviews the look** before the rest of the UI is built (ask).

## Phase 3 — API and LLM (L)
B10 LLM layer, B11 MCP and agent, B12 to B17 APIs, B19 engine explorer API.
- LLM calls verified against real API docs before coding.
- Contract tests for every model failure mode.

**Checkpoint P3:** the full API works with a mocked LLM and, with keys, with real calls. Report both honestly.

## Phase 4 — Feature screens (L)
F4 members, F5 menu, F6 prescription, F7 log, F8 stock, F9 patient and reminders, F10 bazar, F11 dashboard, F12 engine, eval and how-it-works.

**Checkpoint P4:** the full demo flow works in a browser at phone size in both themes: setup, prescription confirm, voice event, daily menu with blocked and split, Review with guests, patient button, missed-dose escalation (via the tick `now` override).

## Phase 5 — PWA, polish, evaluation (M)
F13 PWA and push, F14 polish and Bangla copy review (ask the owner to review Bangla wording), B18 evaluation harness and results page, B20 hardening.

**Checkpoint P5:** evaluation run produced real numbers. Owner reviews.

## Phase 6 — Testing and audit (M to L)
Run everything in `docs/05_TESTING_AND_AUDIT_PLAN.md`: edge cases, dynamic checks, hallucination tests, non-functional checks. Fix or log. Write `docs/AUDIT_REPORT.md`.

**Checkpoint P6:** audit report delivered. Owner decides on open issues.

## Phase 7 — Deploy (S to M) — ask first
- Ask before pushing and before touching Supabase production or Render settings.
- Run migrations and seed on Supabase, deploy backend then frontend on Render, set env vars, set up the tick pinger instructions, warm-up check.
- Smoke test the deployed system with the demo household.

**Checkpoint P7:** deployed link works from a clean browser.

## Phase 8 — Presentation readiness (S)
- Final pass on `docs/ENGINE_LOGIC_BN.md`: every function explained in Bangla, with real code locations and a status table that matches reality.
- Update the Q&A section with answers that match what was actually built.
- Write the README (setup, env vars, how to run tests, how to run the demo, known limitations).
- Prepare the demo seed button and the backup instructions.

---

## When to ask the owner (do not guess)

- Before every `git push` and every cloud or production action.
- Missing keys, accounts or services.
- Anything that looks clinically questionable in the seed data.
- A library or API that does not behave as the docs say.
- A conflict between docs.
- A choice that changes scope, visible behaviour, cost or the demo.
- Bangla wording that you are unsure about.
- Time risk.

## Report format after each milestone

```
Milestone: <name>
Done: <bullets>
Evidence: <commands and short real outputs>
Docs updated: <files>
Issues: <new/open, or none>
Next: <next steps>
Questions: <list, or none>
```

## Final checklist

- [ ] Backend B0 to B20 complete, tests green
- [ ] Frontend F0 to F15 complete, tests green, both themes pass
- [ ] Demo household flow works end to end, locally and deployed
- [ ] Evaluation numbers produced by a real run and shown at `/eval`
- [ ] Hostile-model and prompt-injection tests pass
- [ ] `docs/AUDIT_REPORT.md` written, every claim backed or removed
- [ ] `docs/ENGINE_LOGIC_BN.md` complete, accurate, with real code locations
- [ ] `docs/ISSUES.md` up to date
- [ ] README complete
- [ ] No secrets in git
- [ ] Owner has approved the final push

