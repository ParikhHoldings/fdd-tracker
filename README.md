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

## Ingestion pipeline
The scanner includes a runnable ingestion pipeline that loads filings from JSON adapters.

**Trigger ingestion:**
```bash
curl -X POST http://localhost:8000/ingest/run -H "Content-Type: application/json" -d '{"states": ["CA", "NY"]}'
```

**Source file paths (JSON arrays):**
- FTC filings: `data/sources/ftc_filings.json`
- State portal filings: `data/sources/state_filings.json`

Each FTC record: `{franchise_name, filing_url, filed_on}`
Each state record: `{state, franchise_name, filing_url, filed_on}`

**Refresh state source cache (CA + IL live adapters):**
```bash
curl -X POST http://localhost:8000/ingest/refresh-state-sources -H "Content-Type: application/json" -d '{"states": ["CA", "IL"]}'
```
This updates `data/sources/state_filings.json` with the latest parsed records.

**Watchlist alerts feed:**
```bash
curl "http://localhost:8000/alerts?email=you@example.com&limit=25"
```
Returns recent change summaries for franchises on that watchlist (includes `read` state).

**Mark an alert as read:**
```bash
curl -X POST http://localhost:8000/alerts/read \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","franchise_slug":"chick-fil-a","generated_at":"2026-04-08T00:00:00"}'
```

**Unread count + bulk mark by franchise:**
```bash
curl "http://localhost:8000/alerts/unread-count?email=you@example.com"
curl -X POST "http://localhost:8000/alerts/read/franchise?email=you@example.com&franchise_slug=chick-fil-a"
```


**Filter alerts (risk + unread + franchise):**
```bash
curl "http://localhost:8000/alerts?email=you@example.com&risk_level=high,medium&unread_only=true&franchise_slug=chick-fil-a&limit=25"
```

**Alert summary for dashboards:**
```bash
curl "http://localhost:8000/alerts/summary?email=you@example.com"
```
Returns total/unread counts, risk-level breakdown, and top unread franchises.


**Generate alert digests (writes to outbox JSONL):**
```bash
# Single email
curl -X POST http://localhost:8000/alerts/digest/run \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","max_alerts":25,"mark_read":false}'

# All watchlist emails
curl -X POST http://localhost:8000/alerts/digest/run \
  -H "Content-Type: application/json" \
  -d '{"max_alerts":25,"mark_read":false}'
```

