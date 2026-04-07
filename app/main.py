from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr

app = FastAPI(title="FDD Tracker API", version="0.1.0")

FRANCHISES = [
    {"slug": "chick-fil-a", "name": "Chick-fil-A", "category": "QSR"},
    {"slug": "orangetheory", "name": "Orangetheory", "category": "Fitness"},
]
WATCHLISTS: list[dict] = []
CHANGES = {
    "chick-fil-a": [{"categories": ["fees", "financials"], "risk_level": "medium"}],
    "orangetheory": [{"categories": ["litigation"], "risk_level": "high"}],
}


class WatchlistIn(BaseModel):
    email: EmailStr
    franchise_slug: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/franchises")
def franchises() -> list[dict]:
    return FRANCHISES


@app.post("/watchlists")
def create_watchlist(payload: WatchlistIn) -> dict:
    item = payload.model_dump()
    WATCHLISTS.append(item)
    return {"created": True, "count": len(WATCHLISTS), "item": item}


@app.get("/changes/{franchise_slug}")
def changes(franchise_slug: str) -> dict:
    return {"franchise_slug": franchise_slug, "changes": CHANGES.get(franchise_slug, [])}
