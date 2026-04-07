from datetime import date

from fdd_tracker.models import Filing
from fdd_tracker.services.store import (
    delete_watchlist,
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
