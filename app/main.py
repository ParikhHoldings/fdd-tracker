from __future__ import annotations

from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

from fdd_tracker.db import ensure_db
from fdd_tracker.models import Filing
from fdd_tracker.services.ingest import refresh_state_source_cache, run_ingestion
from fdd_tracker.services.store import (
    delete_watchlist,
    get_alert_feed,
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


@app.post("/ingest/refresh-state-sources")
def refresh_state_sources(payload: RefreshStateSourcesRequest | None = None) -> dict:
    """Refresh state filings from live portal sources and update JSON cache."""
    states = payload.states if payload else None
    return refresh_state_source_cache(states=states)


@app.get("/alerts")
def alerts(email: EmailStr, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"email": email, "alerts": get_alert_feed(email=str(email), limit=limit)}


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
