from __future__ import annotations

from datetime import date, datetime, timezone
from pydantic import BaseModel, Field


class Franchise(BaseModel):
    slug: str
    name: str
    category: str | None = None


class Filing(BaseModel):
    franchise_slug: str
    source: str
    filed_on: date | None = None
    document_url: str
    document_hash: str | None = None


class ChangeSummary(BaseModel):
    franchise_slug: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    categories: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
