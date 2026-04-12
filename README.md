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

**Inspect provider catalog + dispatch outbox queue:**
```bash
curl "http://localhost:8000/alerts/providers"
curl -X POST http://localhost:8000/alerts/providers/smoke-test -H "Content-Type: application/json" -d "{\"provider\":\"noop\",\"email\":\"ops@example.com\",\"dry_run\":true}"
curl "http://localhost:8000/alerts/outbox?limit=25"
curl "http://localhost:8000/alerts/outbox/sent?limit=25&email=ops@example.com&run_id=nightly-2026-04-08"
curl "http://localhost:8000/alerts/outbox/failed?limit=25&email=ops@example.com&run_id=nightly-2026-04-08"
curl "http://localhost:8000/alerts/runs/nightly-2026-04-08/summary"  # includes counts, latest timestamps, artifact file paths, and operational fallback/validation metadata
curl "http://localhost:8000/alerts/runs/nightly-2026-04-08/events"   # per-run event timeline for fallback/degraded triage
curl "http://localhost:8000/alerts/runs/nightly-2026-04-08/events?kind=dispatch-fallback&status=executed"
curl "http://localhost:8000/alerts/runs/latest/summary"
curl "http://localhost:8000/alerts/runs/nightly-2026-04-08/events?kind=dispatch-fallback&status=executed&limit=10&offset=0"
curl "http://localhost:8000/alerts/runs/latest/events?kind=dispatch-fallback"
curl -X POST http://localhost:8000/alerts/outbox/dispatch   -H "Content-Type: application/json"   -d '{"limit":25,"dry_run":true,"provider":"noop"}'
curl -X POST http://localhost:8000/alerts/outbox/dispatch   -H "Content-Type: application/json"   -d '{"limit":25,"dry_run":false,"provider":"resend","confirm_live":true,"idempotency_key":"run-2026-04-10-01","live_min_interval_seconds":60}'
```


**Generate alert digests (writes to outbox JSONL):**
```bash
# Single email
curl -X POST http://localhost:8000/alerts/digest/run \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","max_alerts":25,"mark_read":false,"run_id":"nightly-2026-04-08"}'

# All watchlist emails
curl -X POST http://localhost:8000/alerts/digest/run \
  -H "Content-Type: application/json" \
  -d '{"max_alerts":25,"mark_read":false}'
```


Outbox/sent/failed records now include run metadata fields (`run_id`, `queued_at`, `dispatched_at`, `failed_at`, `retry_count`, `retried_at`) plus delivery metadata (`delivery_mode`, `delivery_provider`, `delivery_status`, `provider_message_id`) for cron auditability.

Provider routing is deterministic: unknown providers are rejected with `error.reason=unsupported-provider`, returns queue counts (`remaining`), and performs no queue mutation.

Live email dispatch is now available via `provider="resend"` when `RESEND_API_KEY` and `ALERTS_FROM_EMAIL` are set.


**Single-shot cron cycle (generate → dispatch → retry):**
```bash
curl -X POST http://localhost:8000/alerts/cron/tick \
  -H "Content-Type: application/json" \
  -d '{"max_alerts":25,"generate_mark_read":false,"dispatch_limit":100,"retry_limit":100,"dispatch_dry_run":true,"dispatch_provider":"noop","run_id":"nightly-2026-04-08","lock_stale_after_seconds":900}'
```

The cron tick is lock-guarded with `data/alerts_cron.lock` and now includes preflight + lock-recovery endpoints for deterministic run-readiness checks and stale lock cleanup. Preflight responses include provider health and dispatch planning metadata (`requested_*`, `effective_*`, `fallback_applied`) so schedulers can verify or auto-fallback before running live mode. Tick responses/history also flag `degraded=true` with `events` entries when dispatch fallback is triggered. It also accepts `dispatch_dry_run`/`dispatch_provider` so scheduler runs can be deterministic in test mode or explicitly provider-routed.
- If another run is active, the endpoint returns `status="skipped_locked"` and writes that event to cron history.
- Stale lock recovery is automatic after `lock_stale_after_seconds` (default 900 seconds).

Example locked response shape:
```json
{"status":"skipped_locked","run_id":"nightly-2026-04-08","lock":{"acquired":false,"lock":{"run_id":"active-run"}}}
```


**Check cron operational status + recent runs:**
```bash
curl "http://localhost:8000/alerts/cron/status?lock_stale_after_seconds=900"
curl -X POST http://localhost:8000/alerts/cron/preflight -H "Content-Type: application/json" -d '{"dispatch_dry_run":true,"dispatch_provider":"noop","lock_stale_after_seconds":900}'
curl -X POST http://localhost:8000/alerts/cron/recover-lock -H "Content-Type: application/json" -d '{"lock_stale_after_seconds":900,"force":false}'
curl "http://localhost:8000/alerts/cron/history/latest"
curl "http://localhost:8000/alerts/cron/history?limit=25"
```


**Prune retained artifact logs (bounded storage):**
```bash
curl -X POST http://localhost:8000/alerts/retention/prune \
  -H "Content-Type: application/json" \
  -d '{"outbox_keep_last":1000,"sent_keep_last":2000,"failed_keep_last":1000,"history_keep_last":2000}'
```
