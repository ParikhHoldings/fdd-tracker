from __future__ import annotations

from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

from fdd_tracker.db import ensure_db
from fdd_tracker.models import Filing
from fdd_tracker.services.alerts import dispatch_outbox, list_outbox, retry_failed_outbox, run_alerts_cron_tick, run_digest_for_all_emails, run_digest_for_email
from fdd_tracker.services.ingest import refresh_state_source_cache, run_ingestion
from fdd_tracker.services.store import (
    delete_watchlist,
    get_alert_feed,
    get_alert_summary,
    get_recent_changes,
    get_unread_alert_count,
    get_watchlists,
    mark_alert_read,
    mark_alerts_read_for_franchise,
    upsert_filing,
    upsert_watchlist,
)

app = FastAPI(title="FDD Tracker API", version="0.2.0")

FRANCHISES = [
    {"slug": "chick-fil-a", "name": "Chick-fil-A", "category": "QSR"},
    {"slug": "orangetheory", "name": "Orangetheory", "category": "Fitness"},
]


class WatchlistIn(BaseModel):
    email: EmailStr
    franchise_slug: str


class FilingIn(BaseModel):
    franchise_slug: str
    source: str
    filed_on: date | None = None
    document_url: str
    document_hash: str | None = None


class IngestRequest(BaseModel):
    states: list[str] | None = None


@app.on_event("startup")
def startup() -> None:
    ensure_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/franchises")
def franchises() -> list[dict]:
    return FRANCHISES


@app.post("/watchlists")
def create_watchlist(payload: WatchlistIn) -> dict:
    result = upsert_watchlist(email=payload.email, franchise_slug=payload.franchise_slug)
    created = result.pop("created")
    return {"created": created, "item": result}


@app.get("/watchlists")
def list_watchlists(email: str | None = Query(default=None)) -> list[dict]:
    return get_watchlists(email=email)


@app.delete("/watchlists")
def remove_watchlist(payload: WatchlistIn) -> dict:
    deleted = delete_watchlist(email=payload.email, franchise_slug=payload.franchise_slug)
    return {"deleted": deleted}


@app.post("/filings")
def create_filing(payload: FilingIn) -> dict:
    changed = upsert_filing(Filing(**payload.model_dump()))
    return {"stored": True, "changed_rows": changed}


@app.get("/changes/{franchise_slug}")
def changes(franchise_slug: str, limit: int = Query(default=20, ge=1, le=200)) -> dict:
    return {
        "franchise_slug": franchise_slug,
        "changes": get_recent_changes(franchise_slug=franchise_slug, limit=limit),
    }


@app.post("/ingest/run")
def ingest_run(payload: IngestRequest | None = None) -> dict:
    states = payload.states if payload else None
    return run_ingestion(states=states)


class RefreshStateSourcesRequest(BaseModel):
    states: list[str] | None = None


class AlertReadIn(BaseModel):
    email: EmailStr
    franchise_slug: str
    generated_at: str


class AlertDigestRunIn(BaseModel):
    email: EmailStr | None = None
    max_alerts: int = 25
    mark_read: bool = False
    run_id: str | None = None


class AlertOutboxDispatchIn(BaseModel):
    limit: int = 100


class AlertOutboxRetryIn(BaseModel):
    limit: int = 100


class AlertCronTickIn(BaseModel):
    max_alerts: int = 25
    generate_mark_read: bool = False
    dispatch_limit: int = 100
    retry_limit: int = 100
    run_id: str | None = None


@app.post("/ingest/refresh-state-sources")
def refresh_state_sources(payload: RefreshStateSourcesRequest | None = None) -> dict:
    """Refresh state filings from live portal sources and update JSON cache."""
    states = payload.states if payload else None
    return refresh_state_source_cache(states=states)


@app.get("/alerts")
def alerts(
    email: EmailStr,
    limit: int = Query(default=50, ge=1, le=200),
    risk_level: str | None = Query(default=None, description="Comma-separated: low,medium,high"),
    unread_only: bool = Query(default=False),
    franchise_slug: str | None = Query(default=None),
) -> dict:
    risk_levels = [item.strip().lower() for item in risk_level.split(",") if item.strip()] if risk_level else None
    return {
        "email": email,
        "alerts": get_alert_feed(
            email=str(email),
            limit=limit,
            risk_levels=risk_levels,
            unread_only=unread_only,
            franchise_slug=franchise_slug,
        ),
    }


@app.post("/alerts/read")
def alerts_read(payload: AlertReadIn) -> dict:
    marked = mark_alert_read(
        email=str(payload.email),
        franchise_slug=payload.franchise_slug,
        generated_at=payload.generated_at,
    )
    return {"marked": bool(marked), "created": marked}


@app.post("/alerts/read/franchise")
def alerts_read_franchise(email: EmailStr, franchise_slug: str) -> dict:
    marked = mark_alerts_read_for_franchise(email=str(email), franchise_slug=franchise_slug)
    return {"marked": marked}


@app.get("/alerts/unread-count")
def alerts_unread_count(email: EmailStr) -> dict:
    return {"email": email, "unread_count": get_unread_alert_count(email=str(email))}


@app.get("/alerts/summary")
def alerts_summary(email: EmailStr) -> dict:
    return {"email": email, **get_alert_summary(email=str(email))}


@app.post("/alerts/digest/run")
def alerts_digest_run(payload: AlertDigestRunIn) -> dict:
    max_alerts = max(1, min(payload.max_alerts, 200))
    if payload.email:
        return run_digest_for_email(
            email=str(payload.email),
            max_alerts=max_alerts,
            mark_read=payload.mark_read,
            run_id=payload.run_id,
        )
    return run_digest_for_all_emails(max_alerts=max_alerts, mark_read=payload.mark_read, run_id=payload.run_id)


@app.get("/alerts/outbox")
def alerts_outbox(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": list_outbox(limit=limit)}


@app.post("/alerts/outbox/dispatch")
def alerts_outbox_dispatch(payload: AlertOutboxDispatchIn) -> dict:
    limit = max(1, min(payload.limit, 500))
    return dispatch_outbox(limit=limit)


@app.post("/alerts/outbox/retry-failed")
def alerts_outbox_retry_failed(payload: AlertOutboxRetryIn) -> dict:
    limit = max(1, min(payload.limit, 500))
    return retry_failed_outbox(limit=limit)


@app.post("/alerts/cron/tick")
def alerts_cron_tick(payload: AlertCronTickIn) -> dict:
    return run_alerts_cron_tick(
        max_alerts=max(1, min(payload.max_alerts, 200)),
        generate_mark_read=payload.generate_mark_read,
        dispatch_limit=max(1, min(payload.dispatch_limit, 500)),
        retry_limit=max(1, min(payload.retry_limit, 500)),
        run_id=payload.run_id,
    )
