# 01 — Product and Guardrails

## 1. One-paragraph idea

Harbor is a Bangla-first web app for households where one or more members live with chronic conditions (diabetes, high blood pressure, kidney disease, high uric acid, food allergies). One caregiver, usually the person who cooks, manages everyone. Harbor tells the caregiver what is safe to cook tonight for every person in the house, which portion to set aside for whom and at which cooking step (shared-pot cooking), reminds patients to take medicines timed to meals with one big button, and alerts the caregiver when a dose is missed. It also tracks the pantry through voice or text in everyday Bangla, handles events such as guests, and plans a monthly bazar list inside a budget.

**Core design decision:** AI reads and explains; deterministic Python code decides. A validator rejects any model output that is not grounded in tool results.

## 2. Users

| User | Role | Needs |
|---|---|---|
| Caregiver (primary) | Cooks, manages medicines and stock | Safe menu, split instruction, easy logging, bazar list, missed-dose alert |
| Elderly patient | Takes medicines | One huge button, no confusing text |
| Relatives abroad (later version) | Worry from far | Alerts (SMS/WhatsApp) — roadmap, not in demo |

## 3. Feature list (all in scope; nothing is cut without owner approval)

1. Household creation, access code and PIN, consent screen.
2. Member profiles: name, age group, role, conditions, allergies, diet presets.
3. Prescription photo, draft extraction, caregiver confirmation gate, drug class mapping.
4. Safety engine: allergens, drug-food rules, diet presets, age profiles, `UNVERIFIED` fail-safe.
5. Shared-pot engine: safe-as-is or safe-after-one-split dishes, split instruction.
6. Scoring and ranking of safe dishes with a visible breakdown.
7. Daily menu with "why this dish", "why others were blocked", Review button (guests, absences), "cooked" button.
8. Voice and text logging in Bangla/Banglish: Whisper, event parsing, alias matching, quantity normaliser, confirm chips.
9. Inventory as an event log, stock screen, expiry awareness.
10. Monthly bazar list within a budget: seasonal items, estimated prices, safe substitutes.
11. Medicine reminders tied to mealtimes, patient big-button screen, missed-dose escalation to the caregiver, caregiver dose dashboard.
12. Planning agent with a bounded tool loop through the FastMCP tool layer and a tool log.
13. LLM explanation writer, validator, fallback templates.
14. Evaluation harness (30 labelled cases, plain model vs Harbor) and results page.
15. Engine explorer page: pick a member and a recipe, see the exact rule trace (for presentation and Q&A).
16. PWA, light and dark mode, Bangla i18n.
17. Deployment on Render and Supabase, tick endpoint for scheduled work.

## 4. Guardrails (non-negotiable)

1. **AI never decides safety.** Only deterministic code in `core/` decides.
2. **No medicine advice.** Harbor never suggests, changes or stops a medicine, and never states a dose. It only schedules reminders for medicines the caregiver confirmed from a prescription.
3. **Confirmation gate.** Nothing extracted from a prescription photo or from voice/text becomes active until the caregiver confirms it on screen.
4. **Fail safe.** Unknown ingredient, or a medicine that is not mapped to a class, gives `UNVERIFIED` and the dish is not suggested.
5. **Validator before display.** LLM text is shown only after the validator passes. Otherwise a fixed template built from the recipe record is shown.
6. **No model training, no GPU.** Off-the-shelf APIs only.
7. **No clinical claims.** Never say "clinically validated" or "pharmacist reviewed". Say rules "would be reviewed by a pharmacist or dietitian before real use".
8. **No disease names** in notifications, lock screen text or the patient screen. Generic text only ("ওষুধের সময় হয়েছে").
9. **Prices are estimates.** Label every price "আনুমানিক". No scraping of market sites. No live price API exists.
10. **Consent and privacy.** Ask consent before the first prescription photo or voice upload to a third-party API. Do not store prescription images. Keep only confirmed extracted fields.
11. **Seed data is prototype data.** Every seed file carries the header: "Prototype data compiled from general nutrition guidance and pharmacology references. Not clinically reviewed." Do not add clinical rules beyond `SPEC_FULL.md` section 9 without owner approval.

## 5. What the pitch may and may not claim

May claim: the architecture, the rule engine design, measured evaluation numbers produced by the harness, the confirmation gate, the fail-safe behaviour, that estimates are estimates.

May not claim: clinical validation, pharmacist review, live prices, fully automatic reading of handwriting, zero safety violations unless the evaluation run actually shows it, any accuracy number that was not measured.

## 6. Out of scope for the prototype (stated honestly)

Dose advice or changes, replacing doctors, automatic reading of all handwriting without confirmation, live market prices, regional dialect speech recognition, a native mobile app, SMS/WhatsApp alerts to relatives (roadmap), full cost optimisation for the monthly list (a simplified version is built), real authentication beyond household code + PIN (documented as a production requirement), staple (rice, roti) planning.

## 7. Terms

- **Shared-pot (এক হাঁড়িতে রান্না):** one dish for everyone, with an adapted portion set aside at one step.
- **Split step:** the point in a recipe before which a member's portion is taken out (before salt, before green chilli, before the final tempering).
- **Caregiver confirm gate:** the screen where the caregiver reviews and ticks extracted data before it becomes active.
- **UNVERIFIED:** the engine cannot judge this dish (missing data); the dish is not suggested.
- **Tick:** a periodic call that runs all due scheduled work idempotently.

