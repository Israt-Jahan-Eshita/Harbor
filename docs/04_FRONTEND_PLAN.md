# 04 — Frontend Plan (Next.js + Tailwind CSS)

Bangla-first PWA. One route per feature. Connected features may share a page. Backend contracts are in `docs/SPEC_FULL.md` section 13 and `docs/03_BACKEND_PLAN.md`.

> Owner's wording on style: "neumorphism and skeuomorphism, also glass, both modes; light theme for now, not blue, purple or green."
> Confirmed with owner (ISSUE-003): **light mode and dark mode both exist**; neumorphism and skeuomorphism are the main look; glass (glassmorphism) is used for overlays and bars in both modes.

---

## 1. Design language

Three materials, each with a job:

| Material | Used for | Notes |
|---|---|---|
| **Neumorphism** (soft raised and inset surfaces) | Cards, buttons, inputs, toggles, tabs, progress, stat tiles | Raised = actionable or content card. Inset = input fields, pressed states, wells. |
| **Skeuomorphism** (tactile, physical look: gradients, highlights, depth, subtle texture) | The patient "খেয়েছি" button (a physical dome button), the pill-box style dose rows, the dish "plate" card header, rule badges that look like stamped tags, toggle switches | Use sparingly so the app stays readable. The patient button is the hero. |
| **Glass** (translucent, blurred) | Top app bar, bottom navigation, modals and sheets, notification toasts, the voice-recording overlay, the "why blocked" panel header | `backdrop-filter: blur`, thin light border, soft shadow. Works in both modes. |

Accessibility overrides everything: neumorphism has weak contrast by nature, so text and focus states must always be strong (see section 5).

### 1.1 Colour tokens (CSS variables, mapped into Tailwind)

**No blue, purple or green hues anywhere in the theme.** The palette is warm: ivory, sand, clay, terracotta, saffron, charcoal, brick.

Light mode (default, WCAG AA verified in `frontend/lib/contrast.ts` & `frontend/styles/tokens.css`):
```
--bg:            #ECE6DB   /* warm ivory-sand base (neumorphic base colour) */
--surface:       #EFE9DE
--surface-elevated: #F6F1E7
--shadow-light:  #FFFFFF
--shadow-dark:   #C9BFAE
--text:          #2B2621   /* 12.16:1 on --bg */
--text-muted:    #62584E   /* 5.64:1 on --bg */
--accent:        #A84925   /* warm terracotta: 4.98:1 on --bg; #FFFDF9 on --accent 5.95:1 */
--accent-strong: #8B391A
--on-accent:     #FFFDF9
--saffron:       #D9A441   /* #2B2621 on --saffron 6.27:1 */
--saffron-text:  #744B04
--on-saffron:    #2B2621
--danger:        #B3402F   /* brick: #FFFDF9 on --danger 5.83:1 */
--on-danger:     #FFFDF9
--ok:            #785B17   /* deep antique gold: #FFFDF9 on --ok 6.42:1 (never green) */
--on-ok:         #FFFDF9
--glass-bg:      rgba(255, 250, 242, 0.72)
--glass-border:  rgba(255, 255, 255, 0.78)
```
Dark mode:
```
--bg:            #1E1A16
--surface:       #26211C
--surface-elevated: #302A24
--shadow-light:  #352E27
--shadow-dark:   #110E0B
--text:          #EFE7DA   /* 13.76:1 on --bg */
--text-muted:    #B8AD9E   /* 7.36:1 on --surface */
--accent:        #E07A52   /* #1E1A16 on --accent 5.89:1 */
--accent-strong: #F09470
--on-accent:     #1E1A16
--saffron:       #E8B04E   /* #1E1A16 on --saffron 8.95:1 */
--saffron-text:  #F0C26E
--on-saffron:    #1E1A16
--danger:        #E97866   /* #1E1A16 on --danger 6.08:1 */
--on-danger:     #1E1A16
--ok:            #D9B25A   /* #1E1A16 on --ok 8.70:1 */
--on-ok:         #1E1A16
--glass-bg:      rgba(46, 40, 33, 0.75)
--glass-border:  rgba(255, 240, 220, 0.18)
```
Status semantics (never colour alone, always icon plus text):
- `SAFE_DIRECT`: deep gold badge, check icon, "নিরাপদ".
- `SAFE_WITH_SPLIT`: saffron badge, split icon, "আলাদা অংশ লাগবে".
- `BLOCKED`: brick badge, stop icon, "বাদ" plus the rule id.
- `UNVERIFIED`: charcoal outline badge, question icon, "যাচাই করা যায়নি".

The agent must check every colour pair for contrast (section 5) and may adjust tokens within the warm family to pass, recording the final values in this file.

### 1.2 Style primitives (implement as Tailwind utilities or component classes)

```
.neu-raised   : background var(--bg); box-shadow: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light); border-radius: 20px
.neu-inset    : background var(--bg); box-shadow: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light)
.neu-pressed  : same as inset, used on :active
.glass        : background var(--glass-bg); backdrop-filter: blur(16px) saturate(120%); border: 1px solid var(--glass-border); box-shadow: 0 8px 30px rgba(0,0,0,0.12)
.skeu-button  : layered gradients (top highlight, bottom shade), inner bevel, drop shadow; pressed state moves down 2px and flattens the shadow
```
Provide a CSS fallback when `backdrop-filter` is unsupported (solid translucent background). Respect `prefers-reduced-motion` (no big animations) and `prefers-reduced-transparency` where supported.

Radius: 16 to 24 px. Spacing scale of 4 px. Large touch targets (at least 48 px; the patient button is huge).

### 1.3 Theme switching
- Light and dark modes; follow the system setting by default; a toggle in settings and the app bar stores the choice locally.
- Implement with a `data-theme` attribute and CSS variables so no component hard-codes colours.
- Add a visual regression check for both modes.

### 1.4 Typography and language
- Bangla web font (for example Noto Sans Bengali via `next/font`), a clean Latin fallback. Verify the font renders conjuncts correctly.
- Base text 16 px or larger; patient screen text much larger.
- All strings in `messages/bn.json` with a 100% key-parity English dictionary `messages/en.json` (verified by Vitest). No hard-coded user-facing strings. A global **বাংলা ↔ English** toggle in the glass top bar and `/settings` (`harbor_locale` in `localStorage`) switches `<html lang>`, UI copy, dynamic `pickLocalized(bn, en)` data, and Bangla/ASCII numerals (`০-৯` vs `0-9`). Store ASCII internally.

---

## 2. Routes (one page per feature; connected things can share)

| Route | Purpose | Main components | API |
|---|---|---|---|
| `/` | Landing with a short explanation and "start" | Hero, three-step explainer | none |
| `/welcome` | Create household or log in (code + PIN), consent screen | Forms (inset inputs), consent card | `POST /households`, `/households/login` |
| `/dashboard` | **Connected overview**: today's menu summary, today's doses, stock alerts, quick actions | Summary tiles, mini dose list, links to feature pages | `GET /households/{id}/state`, `/dashboard/doses` |
| `/members` | Member list, add and edit | Member cards, add sheet | `/members` |
| `/members/[id]` | One member: conditions, allergies, presets, medicines, dose history | Profile form, medicine list, history | `/members/{id}` |
| `/members/[id]/prescription` | Upload, draft table, confirm gate, drug class mapping | Upload dropzone, editable table, confidence highlights, mapping selects | `/members/{id}/prescription`, `/prescriptions/{id}/confirm` |
| `/menu` | **Connected feature page**: daily menu, why chosen, why blocked, split instruction, Review (guests and absences), "cooked" | Dish cards, score breakdown, blocked panel, Review sheet | `/menu/suggest`, `/menu/review`, `/menu/cooked` |
| `/log` | **Connected feature page**: text box, mic button, confirm chips | Recorder overlay (glass), chips list, confirm bar | `/events/parse`, `/events/confirm` |
| `/stock` | Pantry stock, expiry hints, manual edit | Stock list, edit sheet | `/stock` |
| `/bazar` | Monthly list: budget, items, estimated prices, substitutes, purchase tick-off | Budget input, list, badges | `/bazar/*` |
| `/reminders` | Caregiver dose dashboard: taken, pending, missed per patient | Dose timeline, alert banner | `/dashboard/doses` |
| `/patient/[token]` | The patient screen (no login) | Huge skeuomorphic button, minimal text | `/reminders/due`, `/reminders/{id}/taken` |
| `/engine` | **Engine explorer** for the presentation: pick member and recipe, see the exact rule trace | Selectors, trace viewer | `POST /engine/check` |
| `/eval` | Evaluation results: plain model vs Harbor | Results table, notes | `GET /eval/results` |
| `/settings` | Meal times, notification settings, theme, language, consent, demo data loader | Forms, toggles | various |
| `/how-it-works` | Plain explanation of the architecture for demo viewers | Diagram, short text | none |

Layout: a glass top bar (title, theme toggle, language), a glass bottom navigation on phones (Dashboard, Menu, Log, Stock, More) and a side navigation on wide screens. The patient screen has no navigation.

Shared layout, providers (session, theme, i18n, data fetching), error boundary, toasts.

---

## 3. Key screens in detail

### 3.1 `/menu`
- Header: date, meal selector, "আজ কী রান্না করব?" primary button.
- Result: top 3 dish cards (raised). Each card: name, status badge, one or two lines of Bangla explanation (validated LLM text or template), the **split instruction** highlighted, missing ingredients chips, "কেন এই খাবার?" expander showing the score breakdown bars.
- "কেন বাদ?" panel (glass header): excluded dishes with the rule id and a plain Bangla reason per member.
- **Review** button opens a sheet: guest count, guest restrictions, who is away. Submit recalculates.
- "রান্না হয়েছে" button writes COOKED events.
- Clear states: loading skeleton, empty (no safe dish: explain why and show the blocked list), error (fallback message), stale banner after new events.

### 3.2 `/log`
- Large mic button with a recording overlay (glass). Typed input always available.
- After parsing: chips for each proposed event (item, quantity, action). Unrecognised items are highlighted with a picker. One tap to confirm all.
- Nothing is saved before confirm. Show what changed after confirm (stock delta).

### 3.3 `/members/[id]/prescription`
- Upload dropzone (consent check first).
- Draft table: each row has name as written, suggested class, timing, confidence. Low confidence cells highlighted. A tick per row. "নিশ্চিত করুন" enabled only when at least one row is ticked.
- Unknown drug: forced choice of a known class or "not modelled" with a short explanation.
- A reminder that the photo is not stored.

### 3.4 `/patient/[token]`
- Full screen, minimal. When a dose is due: a huge skeuomorphic dome button "খেয়েছি" (very large text), patient name on top, nothing about conditions. After tap: a pressed animation and a calm confirmation. When nothing is due: "এখন কোনো ওষুধ নেই" and the next time.
- Polls the due endpoint every 15 seconds. Works as a PWA.
- Highest contrast in the app; no neumorphic low-contrast text here.

### 3.5 `/engine`
- Select a member profile (from the household) and a recipe; show each rule check line by line (allergen, drug-food, presets, split) with the rule ids and the final status. Built for explaining the logic live and answering questions.

### 3.6 `/dashboard`
- Connected overview only: summaries and links. Detailed work happens on the feature pages.

---

## 4. Data, state and structure

- Data fetching uses `@tanstack/react-query` (`5.108.2`) wrapped in `lib/providers.tsx` (`QueryClientProvider`).
- API client in `lib/api.ts` with typed responses and `Accept-Language` header matching the active `bn|en` locale.
- Session token (`HarborSession`) is stored in `localStorage` (`harbor_session`) for the prototype; production should upgrade to `httpOnly` SameSite cookies.
- Folder structure: `app/` (routes), `components/ui/` (neu and glass primitives), `components/features/` (menu, log, prescription, stock, bazar, reminders), `lib/`, `messages/`, `styles/`.
- `data-testid` attributes on key controls for end-to-end tests.

## 5. Accessibility and quality rules

- Text contrast at least 4.5:1 (3:1 for large text and UI boundaries). Neumorphic components must still show a clear border or outline for inputs and focus (visible focus ring in `--accent`).
- Never rely on colour alone for status (icon plus text).
- Keyboard accessible; semantic HTML; ARIA labels in Bangla.
- Reduced motion respected. Touch targets at least 48 px.
- Responsive, phone first (360 px wide up to desktop). No horizontal scroll.
- Dark mode checked screen by screen.
- Offline: the patient screen shell works offline and shows a clear "no connection" state.

## 6. PWA and notifications

- Manifest with icons, service worker for push and shell caching.
- Subscribe to push after the user opts in (settings). Push text is generic ("ওষুধের সময় হয়েছে").
- iOS needs the PWA installed for push, so polling and the in-app banner remain the safety net.

## 7. Frontend steps (referenced from the roadmap)

- **F0** Bootstrap Next.js + Tailwind + TypeScript, lint, formatter, env, API client skeleton.
- **F1** Design system: tokens, light/dark switch, neu/glass/skeu primitives, base components (Button, Card, Input, Toggle, Badge, Sheet, Toast, Tabs, Skeleton), a `/styleguide` dev page showing all in both modes with contrast check.
- **F2** Layout shell, navigation, i18n, providers, error boundary.
- **F3** `/welcome`, `/settings` (consent, theme, language, meal times).
- **F4** `/members` and `/members/[id]`.
- **F5** `/menu` (core demo screen) against the deterministic backend first.
- **F6** `/members/[id]/prescription`.
- **F7** `/log` with recording, confirm chips.
- **F8** `/stock`.
- **F9** `/patient/[token]` and `/reminders`.
- **F10** `/bazar`.
- **F11** `/dashboard`.
- **F12** `/engine`, `/eval`, `/how-it-works`.
- **F13** PWA, push, offline shell.
- **F14** Polish: empty and error states, loading, animations, copy review with the owner (Bangla wording).
- **F15** Frontend tests (components, Playwright end-to-end flows), accessibility checks, both themes.

## 8. Definition of done (frontend)

Every route in section 2 works against the real backend; both modes pass contrast checks; Bangla renders correctly; end-to-end tests pass; the demo flow works on a phone-sized viewport; this file reflects what was actually built.

