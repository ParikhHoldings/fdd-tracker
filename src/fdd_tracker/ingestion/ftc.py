from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class FTCFilingRecord:
    franchise_name: str
    filing_url: str
    filed_on: str | None


def fetch_ftc_filings() -> Iterable[FTCFilingRecord]:
    """FTC ingestion stub.

    TODO: add real source adapter for public FTC/state filing feeds.
    """
    return []
