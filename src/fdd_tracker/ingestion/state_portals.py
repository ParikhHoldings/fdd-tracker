from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# State portal source URLs (placeholder constants)
# ---------------------------------------------------------------------------
CA_FEED_URL = "https://www.oag.ca.gov/franchise/filings.xml"
IL_FEED_URL = "https://www.ilsos.gov/franchise/filings.xml"

DEFAULT_LIVE_STATES = ["CA", "IL"]


@dataclass
class StatePortalRecord:
    state: str
    franchise_name: str
    filing_url: str
    filed_on: str | None


# ---------------------------------------------------------------------------
# Parsers for state portal feeds (operate on provided text, no network)
# ---------------------------------------------------------------------------


def parse_ca_filings(feed_text: str) -> list[StatePortalRecord]:
    """Parse California franchise filings from feed text.

    Expects XML-like or structured text with franchise entries.
    Extracts franchise_name, filing_url, and optional filed_on date.

    Args:
        feed_text: Raw text from California portal feed.

    Returns:
        List of StatePortalRecord with state='CA'.
    """
    records: list[StatePortalRecord] = []

    # Pattern to extract <item> or <entry> blocks with franchise info
    # Handles XML-style feeds with flexible tag names
    item_pattern = re.compile(
        r"<(?:item|entry)[^>]*>(.*?)</(?:item|entry)>",
        re.DOTALL | re.IGNORECASE,
    )
    name_pattern = re.compile(
        r"<(?:title|franchise[_-]?name|name)>([^<]+)</(?:title|franchise[_-]?name|name)>",
        re.IGNORECASE,
    )
    url_pattern = re.compile(
        r"<(?:link|url|document[_-]?url|filing[_-]?url)>([^<]+)</(?:link|url|document[_-]?url|filing[_-]?url)>",
        re.IGNORECASE,
    )
    # Also support href attribute in link tags
    url_href_pattern = re.compile(
        r'<link[^>]*href=["\']([^"\']+)["\'][^>]*/?>',
        re.IGNORECASE,
    )
    date_pattern = re.compile(
        r"<(?:filed[_-]?on|date|pub[_-]?date|filing[_-]?date)>([^<]+)</(?:filed[_-]?on|date|pub[_-]?date|filing[_-]?date)>",
        re.IGNORECASE,
    )

    for item_match in item_pattern.finditer(feed_text):
        item_text = item_match.group(1)

        name_match = name_pattern.search(item_text)
        url_match = url_pattern.search(item_text) or url_href_pattern.search(item_text)

        if name_match and url_match:
            franchise_name = name_match.group(1).strip()
            filing_url = url_match.group(1).strip()

            date_match = date_pattern.search(item_text)
            filed_on = date_match.group(1).strip() if date_match else None

            # Normalize date to ISO format if possible
            filed_on = _normalize_date(filed_on)

            records.append(
                StatePortalRecord(
                    state="CA",
                    franchise_name=franchise_name,
                    filing_url=filing_url,
                    filed_on=filed_on,
                )
            )

    return records


def parse_il_filings(feed_text: str) -> list[StatePortalRecord]:
    """Parse Illinois franchise filings from feed text.

    Expects XML-like or structured text with franchise entries.
    Extracts franchise_name, filing_url, and optional filed_on date.

    Args:
        feed_text: Raw text from Illinois portal feed.

    Returns:
        List of StatePortalRecord with state='IL'.
    """
    records: list[StatePortalRecord] = []

    # Similar parsing approach to CA but state is IL
    item_pattern = re.compile(
        r"<(?:item|entry|filing)[^>]*>(.*?)</(?:item|entry|filing)>",
        re.DOTALL | re.IGNORECASE,
    )
    name_pattern = re.compile(
        r"<(?:title|franchise[_-]?name|name|company)>([^<]+)</(?:title|franchise[_-]?name|name|company)>",
        re.IGNORECASE,
    )
    url_pattern = re.compile(
        r"<(?:link|url|document[_-]?url|filing[_-]?url)>([^<]+)</(?:link|url|document[_-]?url|filing[_-]?url)>",
        re.IGNORECASE,
    )
    url_href_pattern = re.compile(
        r'<link[^>]*href=["\']([^"\']+)["\'][^>]*/?>',
        re.IGNORECASE,
    )
    date_pattern = re.compile(
        r"<(?:filed[_-]?on|date|pub[_-]?date|filing[_-]?date|effective[_-]?date)>([^<]+)</(?:filed[_-]?on|date|pub[_-]?date|filing[_-]?date|effective[_-]?date)>",
        re.IGNORECASE,
    )

    for item_match in item_pattern.finditer(feed_text):
        item_text = item_match.group(1)

        name_match = name_pattern.search(item_text)
        url_match = url_pattern.search(item_text) or url_href_pattern.search(item_text)

        if name_match and url_match:
            franchise_name = name_match.group(1).strip()
            filing_url = url_match.group(1).strip()

            date_match = date_pattern.search(item_text)
            filed_on = date_match.group(1).strip() if date_match else None

            filed_on = _normalize_date(filed_on)

            records.append(
                StatePortalRecord(
                    state="IL",
                    franchise_name=franchise_name,
                    filing_url=filing_url,
                    filed_on=filed_on,
                )
            )

    return records


def _normalize_date(date_str: str | None) -> str | None:
    """Attempt to normalize a date string to ISO format (YYYY-MM-DD).

    Args:
        date_str: Raw date string from feed.

    Returns:
        ISO formatted date string or original if parsing fails.
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # MM/DD/YYYY format
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if match:
        month, day, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # YYYY/MM/DD format
    match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # Return as-is if we can't parse
    return date_str


def dedupe_records(records: list[StatePortalRecord]) -> list[StatePortalRecord]:
    """Remove duplicate records based on (state, filing_url) tuple.

    Args:
        records: List of StatePortalRecord to deduplicate.

    Returns:
        Deduplicated list preserving first occurrence order.
    """
    seen: set[tuple[str, str]] = set()
    result: list[StatePortalRecord] = []

    for record in records:
        key = (record.state, record.filing_url)
        if key not in seen:
            seen.add(key)
            result.append(record)

    return result


# ---------------------------------------------------------------------------
# Live state filings fetcher
# ---------------------------------------------------------------------------


def fetch_live_state_filings(
    states: list[str] | None = None,
    ca_text: str | None = None,
    il_text: str | None = None,
) -> list[StatePortalRecord]:
    """Fetch and parse state portal filings from live sources or provided text.

    Args:
        states: List of state codes to fetch. Defaults to CA and IL.
        ca_text: If provided, use this text instead of fetching CA feed.
        il_text: If provided, use this text instead of fetching IL feed.

    Returns:
        Deduplicated list of StatePortalRecord from requested states.
    """
    if states is None:
        states = DEFAULT_LIVE_STATES

    all_records: list[StatePortalRecord] = []

    if "CA" in states:
        if ca_text is not None:
            all_records.extend(parse_ca_filings(ca_text))
        else:
            fetched_text = _fetch_url(CA_FEED_URL)
            if fetched_text:
                all_records.extend(parse_ca_filings(fetched_text))

    if "IL" in states:
        if il_text is not None:
            all_records.extend(parse_il_filings(il_text))
        else:
            fetched_text = _fetch_url(IL_FEED_URL)
            if fetched_text:
                all_records.extend(parse_il_filings(fetched_text))

    return dedupe_records(all_records)


def _fetch_url(url: str, timeout: int = 30) -> str | None:
    """Fetch URL content with best-effort error handling.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Response text or None on error.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


# ---------------------------------------------------------------------------
# JSON file loader (existing functionality preserved)
# ---------------------------------------------------------------------------


def fetch_state_filings(states: list[str] | None = None, path: str | None = None) -> Iterable[StatePortalRecord]:
    """Load state portal filing records from a JSON file.

    Args:
        states: Optional list of state codes to filter by.
        path: Path to JSON file. Defaults to data/sources/state_filings.json.

    Returns:
        Iterable of StatePortalRecord. Empty list if file is missing.
    """
    if path is None:
        repo_root = Path(__file__).resolve().parents[3]
        path = str(repo_root / "data" / "sources" / "state_filings.json")

    file_path = Path(path)
    if not file_path.exists():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = [
        StatePortalRecord(
            state=record["state"],
            franchise_name=record["franchise_name"],
            filing_url=record["filing_url"],
            filed_on=record.get("filed_on"),
        )
        for record in data
    ]

    if states:
        records = [r for r in records if r.state in states]

    return records
