# Harbor: Family Care Manager

**Harbor** is a Bangla-first household care web app for multi-condition households (diabetes, hypertension, kidney disease, high uric acid, food allergies) managed by one caregiver.

## Core Design Decision

**AI reads and explains; deterministic Python code decides.**

- **Deterministic Core (`backend/app/core/`):** All food-safety rules (`check_dish_safe`), shared-pot checks (`find_shared_pot_dishes`), scoring, Bangla quantity normalization, inventory math, reminder scheduling, and response validation run in pure Python with zero network or LLM calls.
- **Bounded AI Layer (`backend/app/llm/`):** Handles speech-to-text, informal Bangla event parsing, prescription photo extraction (with all doses stripped), and short Bangla dish explanations—always parsed with Pydantic and verified by `core/validator.py` with fixed Bangla template fallbacks.
- **Caregiver Confirmation Gate:** Nothing extracted from a prescription or voice/text event log becomes active until the caregiver explicitly confirms it on screen.

## Guardrails

1. AI never decides food safety.
2. Harbor never suggests, changes, or stops a medicine, and never states a dose.
3. Caregiver confirmation is required before prescriptions or stock/household events take effect.
4. Unknown ingredients or unmapped medicines evaluate to `UNVERIFIED` and are excluded.
5. Every LLM explanation passes the grounded validator before display, or falls back to a fixed template.
6. Seed rules are prototype data compiled from general nutrition and pharmacology references (**not clinically reviewed**; would require review by a pharmacist or dietitian before real use).
7. Notifications and lock-screen text never include disease or medicine names (`"ওষুধের সময় হয়েছে"`).
8. Prices are labelled approximate (`"আনুমানিক"`).
9. Consent is collected before third-party uploads; prescription images are not stored.

## Verified Stack Versions

### Backend (Python 3.11.9)
- `fastapi==0.165.0`, `uvicorn==0.54.0`
- `pydantic==2.14.4`, `pydantic-settings==2.16.3`
- `sqlalchemy==2.1.9`, `alembic==1.20.1`, `psycopg[binary]==3.3.9`
- `rapidfuzz==3.14.6`, `fastmcp==4.2.4`
- `groq==1.7.0`, `google-genai==3.6.1`
- `pywebpush==2.5.0`, `bcrypt==5.0.0`, `itsdangerous==2.2.0`
- `pytest==9.2.0`, `pytest-asyncio==1.5.0`, `httpx==0.28.1`

## Local Setup (Backend)

1. Ensure PostgreSQL is running (either local PostgreSQL 18 or `docker compose up -d db`) with databases `harbor_dev` and `harbor_test`.
2. Copy `backend/.env.example` to `backend/.env` and fill in `DATABASE_URL`, `TEST_DATABASE_URL`, `SESSION_SECRET`, `TICK_SECRET`, and API keys.
3. Create and activate the virtual environment:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. Run Alembic migrations and load prototype seed data:
   ```powershell
   alembic upgrade head
   python -m app.seed.load
   ```
5. Run the API server and test suite:
   ```powershell
   uvicorn app.main:app --reload
   pytest
   ```
