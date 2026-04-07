from __future__ import annotations

from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

from fdd_tracker.db import ensure_db
from fdd_tracker.models import Filing
from fdd_tracker.services.store import (
    delete_watchlist,
    get_recent_changes,
    get_watchlists,
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
