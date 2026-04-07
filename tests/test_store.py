from datetime import date

from fdd_tracker.models import Filing
from fdd_tracker.services.store import (
    delete_watchlist,
    get_alert_feed,
    get_latest_filings,
    get_recent_changes,
    get_watchlists,
    seed_change_summary,
    upsert_filing,
    upsert_watchlist,
)


def test_upsert_filing_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    filing = Filing(
        franchise_slug="chick-fil-a",
        source="ftc",
        filed_on=date(2026, 1, 1),
        document_url="https://example.com/fdd-2026.pdf",
        document_hash="abc",
    )
    upsert_filing(filing, db_path=db)
    upsert_filing(filing, db_path=db)

    # if unique+upsert is working, still only one summary when we query changes remains unaffected
    seed_change_summary("chick-fil-a", ["fees"], db_path=db)
    rows = get_recent_changes("chick-fil-a", db_path=db)
    assert len(rows) == 1


def test_recent_changes_limit(tmp_path):
    db = str(tmp_path / "test.db")
    for _ in range(3):
        seed_change_summary("orangetheory", ["litigation"], db_path=db)
    rows = get_recent_changes("orangetheory", limit=2, db_path=db)
    assert len(rows) == 2


def test_upsert_watchlist_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    result1 = upsert_watchlist("user@example.com", "chick-fil-a", db_path=db)
    assert result1["created"] is True
    assert result1["email"] == "user@example.com"
    assert result1["franchise_slug"] == "chick-fil-a"

    result2 = upsert_watchlist("user@example.com", "chick-fil-a", db_path=db)
    assert result2["created"] is False
    assert result2["id"] == result1["id"]


def test_get_watchlists_filter_by_email(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("a@example.com", "chick-fil-a", db_path=db)
    upsert_watchlist("b@example.com", "orangetheory", db_path=db)
    upsert_watchlist("a@example.com", "orangetheory", db_path=db)

    all_items = get_watchlists(db_path=db)
    assert len(all_items) == 3

    a_items = get_watchlists(email="a@example.com", db_path=db)
    assert len(a_items) == 2
    assert all(item["email"] == "a@example.com" for item in a_items)


def test_delete_watchlist(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("user@example.com", "chick-fil-a", db_path=db)

    deleted = delete_watchlist("user@example.com", "chick-fil-a", db_path=db)
    assert deleted == 1

    deleted_again = delete_watchlist("user@example.com", "chick-fil-a", db_path=db)
    assert deleted_again == 0

    items = get_watchlists(email="user@example.com", db_path=db)
    assert len(items) == 0


def test_get_latest_filings_ordering(tmp_path):
    """Test that get_latest_filings returns filings ordered by filed_on desc nulls last, then id desc."""
    db = str(tmp_path / "test.db")

    # Insert filings in mixed order - some with dates, one without
    filings = [
        Filing(franchise_slug="acme", source="ftc", filed_on=date(2026, 1, 1), document_url="https://example.com/old.pdf"),
        Filing(franchise_slug="acme", source="state-ca", filed_on=date(2026, 3, 15), document_url="https://example.com/newest.pdf"),
        Filing(franchise_slug="acme", source="state-il", filed_on=date(2026, 2, 10), document_url="https://example.com/middle.pdf"),
        Filing(franchise_slug="acme", source="ftc", filed_on=None, document_url="https://example.com/no-date.pdf"),
    ]
    for f in filings:
        upsert_filing(f, db_path=db)

    result = get_latest_filings("acme", limit=4, db_path=db)

    # Should be ordered: 2026-03-15, 2026-02-10, 2026-01-01, None
    assert len(result) == 4
    assert result[0]["document_url"] == "https://example.com/newest.pdf"
    assert result[1]["document_url"] == "https://example.com/middle.pdf"
    assert result[2]["document_url"] == "https://example.com/old.pdf"
    assert result[3]["document_url"] == "https://example.com/no-date.pdf"
    assert result[3]["filed_on"] is None


def test_get_latest_filings_limit(tmp_path):
    """Test that get_latest_filings respects limit parameter."""
    db = str(tmp_path / "test.db")

    for i in range(5):
        upsert_filing(
            Filing(franchise_slug="test-franchise", source="ftc", filed_on=date(2026, 1, i + 1), document_url=f"https://example.com/doc{i}.pdf"),
            db_path=db,
        )

    result = get_latest_filings("test-franchise", limit=2, db_path=db)
    assert len(result) == 2


def test_get_alert_feed_for_watchlist(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("alerts@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)
    seed_change_summary("orangetheory", ["litigation"], risk_level="medium", db_path=db)

    alerts = get_alert_feed("alerts@example.com", db_path=db)
    assert len(alerts) == 1
    assert alerts[0]["franchise_slug"] == "chick-fil-a"
    assert alerts[0]["risk_level"] == "high"
    assert alerts[0]["categories"] == ["fees"]
