from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class StatePortalRecord:
    state: str
    franchise_name: str
    filing_url: str
    filed_on: str | None


def fetch_state_filings(states: list[str] | None = None) -> Iterable[StatePortalRecord]:
    """State portal ingestion stub.

    TODO: add per-state scrapers for registration states.
    """
    _ = states or ["CA", "IL", "MD", "MI", "MN", "NY", "ND", "SD", "VA", "WA"]
    return []
