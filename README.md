# FDD Tracker

FDD change monitoring for franchise brokers and buyers.

**GitHub:** https://github.com/ParikhHoldings/fdd-tracker  
**Pricing:** $29 Buyer / $99 Broker / $249 Agency

## Core product stack
Next.js 14 + TypeScript + Tailwind · Clerk · Stripe · Resend · Railway (PostgreSQL) · OpenAI

## Added backend scanner scaffold (this run)
This run adds a lightweight Python service scaffold for filing ingestion, diffing, and alerts:
- FastAPI endpoints (`/health`, `/franchises`, `/watchlists`, `/changes/{slug}`)
- Ingestion stubs for FTC + registration-state portals
- PDF extraction fallback utility
- Diff categorization engine for fees/litigation/financials/unit counts
- Pytest coverage for API health and diff behavior

## Next.js setup
```bash
git clone https://github.com/ParikhHoldings/fdd-tracker.git
cd fdd-tracker && git checkout staging && npm install
cp .env.local.example .env.local && npm run dev
```

## Python scanner setup
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
pytest
```
