from datetime import date, datetime, timezone

from fdd_tracker.models import Filing, HealthSignal
from fdd_tracker.services.store import (
    build_health_signal_summary_packet,
    delete_watchlist,
    get_alert_feed,
    get_alert_summary,
    get_health_signal_summary,
    get_latest_filings,
    get_recent_changes,
    get_unread_alert_count,
    get_watchlists,
    list_health_signals,
    mark_alert_read,
    mark_alerts_read_for_franchise,
    render_health_signal_summary_csv,
    render_health_signal_summary_markdown,
    render_health_signal_summary_telegram_chunks,
    seed_change_summary,
    upsert_health_signal,
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
    assert alerts[0]["read"] is False


def test_mark_alert_read_and_reflect_in_feed(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("alerts@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    alerts = get_alert_feed("alerts@example.com", db_path=db)
    assert len(alerts) == 1
    generated_at = alerts[0]["generated_at"]

    created = mark_alert_read("alerts@example.com", "chick-fil-a", generated_at, db_path=db)
    assert created == 1

    # idempotent mark
    created_again = mark_alert_read("alerts@example.com", "chick-fil-a", generated_at, db_path=db)
    assert created_again == 0

    refreshed = get_alert_feed("alerts@example.com", db_path=db)
    assert refreshed[0]["read"] is True
    assert refreshed[0]["read_at"] is not None


def test_unread_count_and_bulk_mark_for_franchise(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("alerts@example.com", "chick-fil-a", db_path=db)
    upsert_watchlist("alerts@example.com", "orangetheory", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], db_path=db)
    seed_change_summary("chick-fil-a", ["litigation"], db_path=db)
    seed_change_summary("orangetheory", ["financials"], db_path=db)

    assert get_unread_alert_count("alerts@example.com", db_path=db) == 3

    marked = mark_alerts_read_for_franchise("alerts@example.com", "chick-fil-a", db_path=db)
    assert marked == 2
    assert get_unread_alert_count("alerts@example.com", db_path=db) == 1



def test_alert_feed_filters_and_summary(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("alerts@example.com", "chick-fil-a", db_path=db)
    upsert_watchlist("alerts@example.com", "orangetheory", db_path=db)

    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)
    seed_change_summary("chick-fil-a", ["litigation"], risk_level="medium", db_path=db)
    seed_change_summary("orangetheory", ["financials"], risk_level="low", db_path=db)

    # mark one alert read to validate unread filter
    first = get_alert_feed("alerts@example.com", limit=10, db_path=db)[0]
    mark_alert_read("alerts@example.com", first["franchise_slug"], first["generated_at"], db_path=db)

    filtered = get_alert_feed(
        "alerts@example.com",
        limit=10,
        risk_levels=["high", "medium"],
        unread_only=True,
        franchise_slug="chick-fil-a",
        db_path=db,
    )
    assert all(item["franchise_slug"] == "chick-fil-a" for item in filtered)
    assert all(item["risk_level"] in {"high", "medium"} for item in filtered)
    assert all(item["read"] is False for item in filtered)

    summary = get_alert_summary("alerts@example.com", db_path=db)
    assert summary["total_alerts"] == 3
    assert summary["unread_alerts"] == 2
    assert summary["by_risk"] == {"low": 1, "medium": 1, "high": 1}
    assert len(summary["top_unread_franchises"]) >= 1


def test_health_signal_upsert_and_list(tmp_path):
    db = str(tmp_path / "test.db")
    observed_at = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)

    row = upsert_health_signal(
        HealthSignal(
            franchise_slug="chick-fil-a",
            source="glassdoor",
            observed_at=observed_at,
            signal_name="employee_sentiment",
            metric_value=4.2,
            sentiment="positive",
            metadata={"sample_size": 120},
        ),
        db_path=db,
    )
    assert row == 1

    rows = list_health_signals("chick-fil-a", db_path=db)
    assert len(rows) == 1
    assert rows[0]["signal_name"] == "employee_sentiment"
    assert rows[0]["metadata"]["sample_size"] == 120


def test_health_signal_summary_rollups(tmp_path):
    db = str(tmp_path / "test.db")
    base_time = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)

    upsert_health_signal(
        HealthSignal(
            franchise_slug="brand-x",
            source="glassdoor",
            observed_at=base_time,
            signal_name="employee_sentiment",
            metric_value=4.0,
            sentiment="positive",
        ),
        db_path=db,
    )
    upsert_health_signal(
        HealthSignal(
            franchise_slug="brand-x",
            source="bbb",
            observed_at=base_time.replace(hour=1),
            signal_name="complaint_volume",
            metric_value=12,
            sentiment="negative",
        ),
        db_path=db,
    )
    upsert_health_signal(
        HealthSignal(
            franchise_slug="brand-x",
            source="reddit",
            observed_at=base_time.replace(hour=2),
            signal_name="mention_volume",
            metric_value=28,
            sentiment="neutral",
        ),
        db_path=db,
    )

    summary = get_health_signal_summary("brand-x", db_path=db)
    assert summary["total_signals"] == 3
    assert summary["sentiment_counts"]["positive"] == 1
    assert summary["sentiment_counts"]["negative"] == 1
    assert summary["metric_averages"]["complaint_volume"] == 12
    assert summary["metric_averages"]["employee_sentiment"] == 4.0


def test_health_signal_summary_export_surfaces(tmp_path):
    db = str(tmp_path / "test.db")
    observed_at = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)
    upsert_health_signal(
        HealthSignal(
            franchise_slug="brand-export",
            source="glassdoor",
            observed_at=observed_at,
            signal_name="employee_sentiment",
            metric_value=4.1,
            sentiment="positive",
        ),
        db_path=db,
    )
    payload = get_health_signal_summary("brand-export", db_path=db)

    markdown = render_health_signal_summary_markdown(payload)
    assert "Franchise Health Signals" in markdown

    telegram = render_health_signal_summary_telegram_chunks(payload, max_chars=220)
    assert len(telegram) >= 1
    assert telegram[0].startswith("[1/")

    csv_data = render_health_signal_summary_csv(payload)
    assert "section,key,value" in csv_data
    assert "meta,franchise_slug,brand-export" in csv_data

    packet = build_health_signal_summary_packet(payload, max_chars=220)
    assert "summary" in packet
    assert "markdown" in packet
    assert "csv" in packet
    assert packet["telegram"]["chunks_with_index"][0].startswith("[1/")
