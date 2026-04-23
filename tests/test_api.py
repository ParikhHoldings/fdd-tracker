from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from fdd_tracker.services.store import seed_change_summary

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_filing():
    payload = {
        "franchise_slug": "chick-fil-a",
        "source": "ftc",
        "filed_on": "2026-01-01",
        "document_url": "https://example.com/fdd.pdf",
        "document_hash": "xyz",
    }
    r = client.post("/filings", json=payload)
    assert r.status_code == 200
    assert r.json()["stored"] is True


def test_changes_endpoint_limit():
    seed_change_summary("chick-fil-a", ["fees"])
    seed_change_summary("chick-fil-a", ["litigation"])
    r = client.get("/changes/chick-fil-a?limit=1")
    assert r.status_code == 200
    assert len(r.json()["changes"]) == 1


def test_health_signals_endpoints():
    slug = f"health-{uuid4().hex[:8]}"

    create = client.post(
        "/health-signals",
        json={
            "franchise_slug": slug,
            "source": "glassdoor",
            "observed_at": "2026-04-23T00:00:00Z",
            "signal_name": "employee_sentiment",
            "metric_value": 4.3,
            "sentiment": "positive",
            "metadata": {"sample_size": 52},
        },
    )
    assert create.status_code == 200
    assert create.json()["stored"] is True

    listing = client.get(f"/health-signals/{slug}?limit=10")
    assert listing.status_code == 200
    list_data = listing.json()
    assert list_data["franchise_slug"] == slug
    assert len(list_data["signals"]) == 1
    assert list_data["signals"][0]["source"] == "glassdoor"

    summary = client.get(f"/health-signals/{slug}/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["franchise_slug"] == slug
    assert summary_data["total_signals"] == 1
    assert summary_data["sentiment_counts"]["positive"] == 1


def test_health_signals_summary_export_endpoints():
    slug = f"health-export-{uuid4().hex[:8]}"
    create = client.post(
        "/health-signals",
        json={
            "franchise_slug": slug,
            "source": "bbb",
            "observed_at": "2026-04-23T00:00:00Z",
            "signal_name": "complaint_volume",
            "metric_value": 9,
            "sentiment": "negative",
        },
    )
    assert create.status_code == 200

    md = client.get(f"/health-signals/{slug}/summary/markdown")
    assert md.status_code == 200
    assert "Franchise Health Signals" in md.json()["markdown"]

    tg = client.get(f"/health-signals/{slug}/summary/telegram?max_chars=220")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get(f"/health-signals/{slug}/summary/csv")
    assert csv_resp.status_code == 200
    assert "section,key,value" in csv_resp.json()["csv"]

    packet = client.get(f"/health-signals/{slug}/summary/packet?max_chars=220")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "summary" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert packet_data["telegram"]["chunks_with_index"][0].startswith("[1/")


def test_change_insights_endpoint_shape_and_counts():
    slug = f"insights-{uuid4().hex[:8]}"
    seed_change_summary(slug, ["fees", "litigation"], risk_level="high")
    seed_change_summary(slug, ["fees"], risk_level="medium")
    seed_change_summary(slug, ["financials"], risk_level="low")

    r = client.get(f"/changes/{slug}/insights?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["franchise_slug"] == slug
    assert data["total_changes"] == 3
    assert data["by_risk"]["high"] == 1
    assert data["by_risk"]["medium"] == 1
    assert data["by_risk"]["low"] == 1
    assert data["category_counts"]["fees"] == 2
    assert data["latest_change_at"] is not None
    assert data["first_change_at"] is not None
    assert data["risk_trend_last_5"]["window"] == 3
    assert len(data["risk_trend_last_5"]["series"]) == 3


def test_change_insights_endpoint_empty():
    slug = f"insights-empty-{uuid4().hex[:8]}"
    r = client.get(f"/changes/{slug}/insights")
    assert r.status_code == 200
    data = r.json()
    assert data["franchise_slug"] == slug
    assert data["total_changes"] == 0
    assert data["latest_change_at"] is None
    assert data["first_change_at"] is None
    assert data["category_counts"] == {}
    assert data["risk_trend_last_5"]["window"] == 0
    assert data["risk_trend_last_5"]["series"] == []


def test_change_comparisons_endpoint_shape_and_signal():
    left = f"compare-left-{uuid4().hex[:8]}"
    right = f"compare-right-{uuid4().hex[:8]}"

    seed_change_summary(left, ["fees", "litigation"], risk_level="high")
    seed_change_summary(left, ["fees"], risk_level="high")
    seed_change_summary(right, ["fees"], risk_level="low")
    seed_change_summary(right, ["financials"], risk_level="low")

    r = client.get(f"/change-comparisons?left_slug={left}&right_slug={right}&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["left"]["franchise_slug"] == left
    assert data["right"]["franchise_slug"] == right
    assert data["comparison"]["higher_recent_risk"] == left
    assert "fees" in data["comparison"]["shared_categories"]


def test_change_comparisons_endpoint_tie_on_empty():
    left = f"compare-empty-left-{uuid4().hex[:8]}"
    right = f"compare-empty-right-{uuid4().hex[:8]}"
    r = client.get(f"/change-comparisons?left_slug={left}&right_slug={right}")
    assert r.status_code == 200
    data = r.json()
    assert data["comparison"]["higher_recent_risk"] == "tie"
    assert data["comparison"]["change_volume_delta"] == 0


def test_change_comparisons_export_surfaces():
    left = f"compare-export-left-{uuid4().hex[:8]}"
    right = f"compare-export-right-{uuid4().hex[:8]}"
    seed_change_summary(left, ["fees"], risk_level="high")
    seed_change_summary(right, ["fees"], risk_level="low")

    md = client.get(f"/change-comparisons/markdown?left_slug={left}&right_slug={right}")
    assert md.status_code == 200
    assert "# Franchise Change Comparison" in md.json()["markdown"]

    tg = client.get(f"/change-comparisons/telegram?left_slug={left}&right_slug={right}&max_chars=220")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get(f"/change-comparisons/csv?left_slug={left}&right_slug={right}")
    assert csv_resp.status_code == 200
    assert "left_slug,right_slug,higher_recent_risk" in csv_resp.json()["csv"]

    packet = client.get(f"/change-comparisons/packet?left_slug={left}&right_slug={right}&max_chars=220")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "comparison" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_change_comparisons_options_and_exports():
    options = client.get("/change-comparisons/options")
    assert options.status_code == 200
    options_data = options.json()
    assert options_data["defaults"]["limit"] == 200
    assert options_data["constraints"]["max_chars"]["max"] == 10000

    md = client.get("/change-comparisons/options/markdown")
    assert md.status_code == 200
    assert "# Change Comparison Options" in md.json()["markdown"]

    tg = client.get("/change-comparisons/options/telegram?max_chars=220")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get("/change-comparisons/options/csv")
    assert csv_resp.status_code == 200
    assert "section,key,value" in csv_resp.json()["csv"]

    packet = client.get("/change-comparisons/options/packet?max_chars=220")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "options" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_buyer_report_comparison_brief_bundle():
    email = f"buyerbundle-{uuid4().hex[:8]}@example.com"
    left = f"buyer-left-{uuid4().hex[:8]}"
    right = f"buyer-right-{uuid4().hex[:8]}"

    client.post("/watchlists", json={"email": email, "franchise_slug": left})
    client.post("/watchlists", json={"email": email, "franchise_slug": right})
    seed_change_summary(left, ["fees"], risk_level="high")
    seed_change_summary(right, ["financials"], risk_level="low")

    r = client.get(
        f"/buyer-reports/comparison-brief?email={email}&left_slug={left}&right_slug={right}&days=7&max_alerts=50&comparison_limit=50&max_chars=220"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert "weekly_brief" in data
    assert "comparison" in data
    assert "comparison_packet" in data
    assert "summary_markdown" in data
    assert data["comparison"]["left"]["franchise_slug"] == left
    assert data["comparison_packet"]["telegram"]["chunks_with_index"][0].startswith("[1/")
    assert data["health_summaries"] is None


def test_buyer_report_comparison_brief_bundle_with_health_signals():
    email = f"buyerbundle-health-{uuid4().hex[:8]}@example.com"
    left = f"buyer-health-left-{uuid4().hex[:8]}"
    right = f"buyer-health-right-{uuid4().hex[:8]}"

    client.post("/watchlists", json={"email": email, "franchise_slug": left})
    client.post("/watchlists", json={"email": email, "franchise_slug": right})
    seed_change_summary(left, ["fees"], risk_level="high")
    seed_change_summary(right, ["financials"], risk_level="low")
    client.post(
        "/health-signals",
        json={
            "franchise_slug": left,
            "source": "glassdoor",
            "observed_at": "2026-04-23T00:00:00Z",
            "signal_name": "employee_sentiment",
            "metric_value": 4.2,
            "sentiment": "positive",
        },
    )
    client.post(
        "/health-signals",
        json={
            "franchise_slug": right,
            "source": "bbb",
            "observed_at": "2026-04-23T01:00:00Z",
            "signal_name": "complaint_volume",
            "metric_value": 9,
            "sentiment": "negative",
        },
    )

    r = client.get(
        f"/buyer-reports/comparison-brief?email={email}&left_slug={left}&right_slug={right}&include_health_signals=true&health_limit=50"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["include_health_signals"] is True
    assert data["health_summaries"]["left"]["franchise_slug"] == left
    assert data["health_summaries"]["right"]["franchise_slug"] == right
    assert "Health signals (left/right):" in data["summary_markdown"]


def test_buyer_report_comparison_brief_options_and_exports():
    email = f"buyerbundle-exports-{uuid4().hex[:8]}@example.com"
    left = f"buyer-export-left-{uuid4().hex[:8]}"
    right = f"buyer-export-right-{uuid4().hex[:8]}"
    client.post("/watchlists", json={"email": email, "franchise_slug": left})
    client.post("/watchlists", json={"email": email, "franchise_slug": right})
    seed_change_summary(left, ["fees"], risk_level="high")
    seed_change_summary(right, ["financials"], risk_level="low")

    options = client.get("/buyer-reports/comparison-brief/options")
    assert options.status_code == 200
    options_data = options.json()
    assert options_data["defaults"]["days"] == 7
    assert options_data["defaults"]["include_health_signals"] is False
    assert options_data["defaults"]["health_limit"] == 200
    assert options_data["defaults"]["template_variant"] == "executive"
    assert "/buyer-reports/comparison-brief/packet" in options_data["surfaces"]["packet"]
    assert "/buyer-reports/comparison-brief/templates" in options_data["surfaces"]["templates"]

    md = client.get(f"/buyer-reports/comparison-brief/markdown?email={email}&left_slug={left}&right_slug={right}")
    assert md.status_code == 200
    assert "Buyer Report Bundle" in md.json()["markdown"]

    tg = client.get(f"/buyer-reports/comparison-brief/telegram?email={email}&left_slug={left}&right_slug={right}&max_chars=220")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get(f"/buyer-reports/comparison-brief/csv?email={email}&left_slug={left}&right_slug={right}")
    assert csv_resp.status_code == 200
    assert "email,left_slug,right_slug,total_alerts" in csv_resp.json()["csv"]

    packet = client.get(f"/buyer-reports/comparison-brief/packet?email={email}&left_slug={left}&right_slug={right}&max_chars=220")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "bundle" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data

    templates = client.get(
        f"/buyer-reports/comparison-brief/templates?email={email}&left_slug={left}&right_slug={right}&template_variant=analyst"
    )
    assert templates.status_code == 200
    templates_data = templates.json()
    assert templates_data["selected"] == "analyst"
    assert "executive" in templates_data["variants"]
    assert "analyst" in templates_data["variants"]
    assert "concise" in templates_data["variants"]

    templates_packet = client.get(
        f"/buyer-reports/comparison-brief/templates/packet?email={email}&left_slug={left}&right_slug={right}&template_variant=concise&max_chars=220"
    )
    assert templates_packet.status_code == 200
    templates_packet_data = templates_packet.json()
    assert templates_packet_data["selected"] == "concise"
    assert "telegram" in templates_packet_data
    assert templates_packet_data["telegram"]["chunks_with_index"][0].startswith("[1/")


def test_create_watchlist_idempotency():
    payload = {"email": f"test-{uuid4().hex[:8]}@example.com", "franchise_slug": "chick-fil-a"}
    r1 = client.post("/watchlists", json=payload)
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["created"] is True
    assert data1["item"]["email"] == payload["email"]

    r2 = client.post("/watchlists", json=payload)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["created"] is False
    assert data2["item"]["id"] == data1["item"]["id"]


def test_get_watchlists_filter_by_email():
    alice = f"alice-{uuid4().hex[:8]}@example.com"
    bob = f"bob-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": alice, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": bob, "franchise_slug": "orangetheory"})
    client.post("/watchlists", json={"email": alice, "franchise_slug": "orangetheory"})

    r = client.get(f"/watchlists?email={alice}")
    assert r.status_code == 200
    items = r.json()
    assert all(item["email"] == alice for item in items)


def test_delete_watchlist_endpoint():
    payload = {"email": f"delete-{uuid4().hex[:8]}@example.com", "franchise_slug": "chick-fil-a"}
    client.post("/watchlists", json=payload)

    r = client.request("DELETE", "/watchlists", json=payload)
    assert r.status_code == 200
    assert r.json()["deleted"] == 1

    r2 = client.request("DELETE", "/watchlists", json=payload)
    assert r2.status_code == 200
    assert r2.json()["deleted"] == 0


def test_ingest_run_returns_summary_keys():
    r = client.post("/ingest/run", json={})
    assert r.status_code == 200
    data = r.json()
    assert "total_seen" in data
    assert "inserted_or_updated" in data
    assert "sources_breakdown" in data
    assert "ftc" in data["sources_breakdown"]
    assert "state" in data["sources_breakdown"]
    assert "change_summaries_created" in data


def test_ingest_run_with_states_filter():
    r = client.post("/ingest/run", json={"states": ["CA", "NY"]})
    assert r.status_code == 200
    data = r.json()
    assert "total_seen" in data
    assert "sources_breakdown" in data


def test_refresh_state_sources_summary_shape():
    r = client.post("/ingest/refresh-state-sources", json={"states": ["CA", "IL"]})
    assert r.status_code == 200
    data = r.json()
    assert "written" in data
    assert "output_path" in data
    assert "records" in data


def test_alerts_endpoint_returns_watchlist_alerts():
    email = f"alerts-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts?email={email}&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert isinstance(data["alerts"], list)
    assert len(data["alerts"]) >= 1
    assert all(item["franchise_slug"] == "chick-fil-a" for item in data["alerts"])
    assert "read" in data["alerts"][0]


def test_alerts_read_endpoint_marks_alert():
    email = f"alertsread-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    feed = client.get(f"/alerts?email={email}&limit=1")
    generated_at = feed.json()["alerts"][0]["generated_at"]

    mark = client.post(
        "/alerts/read",
        json={"email": email, "franchise_slug": "chick-fil-a", "generated_at": generated_at},
    )
    assert mark.status_code == 200
    assert mark.json()["marked"] is True

    feed2 = client.get(f"/alerts?email={email}&limit=1")
    assert feed2.json()["alerts"][0]["read"] is True


def test_alerts_unread_count_and_bulk_mark_endpoints():
    email = f"alertscount-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("chick-fil-a", ["litigation"], risk_level="medium")
    seed_change_summary("orangetheory", ["financials"], risk_level="low")

    count_before = client.get(f"/alerts/unread-count?email={email}")
    assert count_before.status_code == 200
    assert count_before.json()["unread_count"] >= 3

    bulk = client.post(f"/alerts/read/franchise?email={email}&franchise_slug=chick-fil-a")
    assert bulk.status_code == 200
    assert bulk.json()["marked"] >= 2

    count_after = client.get(f"/alerts/unread-count?email={email}")
    assert count_after.status_code == 200
    assert count_after.json()["unread_count"] <= count_before.json()["unread_count"] - 2



def test_alerts_endpoint_filters():
    email = f"alertsfilter-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("chick-fil-a", ["litigation"], risk_level="medium")
    seed_change_summary("orangetheory", ["financials"], risk_level="low")

    # mark one as read, then request unread high/medium only for chick-fil-a
    base_feed = client.get(f"/alerts?email={email}&limit=10").json()["alerts"]
    first = base_feed[0]
    client.post(
        "/alerts/read",
        json={"email": email, "franchise_slug": first["franchise_slug"], "generated_at": first["generated_at"]},
    )

    r = client.get(
        f"/alerts?email={email}&limit=10&risk_level=high,medium&unread_only=true&franchise_slug=chick-fil-a"
    )
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    assert all(a["franchise_slug"] == "chick-fil-a" for a in alerts)
    assert all(a["risk_level"] in {"high", "medium"} for a in alerts)
    assert all(a["read"] is False for a in alerts)


def test_alerts_summary_endpoint():
    email = f"alertssummary-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("chick-fil-a", ["litigation"], risk_level="medium")
    seed_change_summary("orangetheory", ["financials"], risk_level="low")

    # Mark one read so unread math is non-trivial
    base_feed = client.get(f"/alerts?email={email}&limit=10").json()["alerts"]
    first = base_feed[0]
    client.post(
        "/alerts/read",
        json={"email": email, "franchise_slug": first["franchise_slug"], "generated_at": first["generated_at"]},
    )

    r = client.get(f"/alerts/summary?email={email}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_alerts"] >= 3
    assert data["unread_alerts"] >= 2
    assert data["by_risk"]["low"] >= 1
    assert data["by_risk"]["medium"] >= 1
    assert data["by_risk"]["high"] >= 1
    assert isinstance(data["top_unread_franchises"], list)


def test_alerts_weekly_brief_endpoint_default_window():
    email = f"weeklybrief-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("chick-fil-a", ["litigation"], risk_level="medium")

    r = client.get(f"/alerts/weekly-brief?email={email}")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert data["window_days"] == 7
    assert data["total_alerts"] >= 2
    assert data["by_risk"]["high"] >= 1
    assert data["by_risk"]["medium"] >= 1
    assert isinstance(data["top_franchises"], list)


def test_alerts_weekly_brief_endpoint_custom_window_and_max_alerts():
    email = f"weeklybriefcustom-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "orangetheory"})
    seed_change_summary("orangetheory", ["financials"], risk_level="low")

    r = client.get(f"/alerts/weekly-brief?email={email}&days=3&max_alerts=1")
    assert r.status_code == 200
    data = r.json()
    assert data["window_days"] == 3
    assert data["total_alerts"] <= 1
    assert data["by_risk"]["low"] >= 0


def test_alerts_weekly_brief_markdown_endpoint():
    email = f"weeklybriefmd-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/weekly-brief/markdown?email={email}&days=7&max_alerts=20")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert "# Weekly Brief" in data["markdown"]


def test_alerts_weekly_brief_telegram_csv_packet_endpoints():
    email = f"weeklybriefexports-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "orangetheory"})
    seed_change_summary("orangetheory", ["fees"], risk_level="medium")

    tg = client.get(f"/alerts/weekly-brief/telegram?email={email}&max_chars=500")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert isinstance(tg_data["chunks_with_index"], list)

    csv_resp = client.get(f"/alerts/weekly-brief/csv?email={email}")
    assert csv_resp.status_code == 200
    assert "email,window_days,total_alerts" in csv_resp.json()["csv"]

    packet = client.get(f"/alerts/weekly-brief/packet?email={email}&max_chars=500")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "brief" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_alerts_weekly_brief_options_endpoint():
    r = client.get("/alerts/weekly-brief/options")
    assert r.status_code == 200
    data = r.json()
    assert "constraints" in data
    assert data["defaults"]["days"] == 7
    assert "/alerts/weekly-brief/packet" in data["surfaces"]["packet"]


def test_alerts_weekly_brief_options_presentation_endpoints():
    md = client.get("/alerts/weekly-brief/options/markdown")
    assert md.status_code == 200
    assert "# Weekly Brief Options" in md.json()["markdown"]

    tg = client.get("/alerts/weekly-brief/options/telegram?max_chars=200")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get("/alerts/weekly-brief/options/csv")
    assert csv_resp.status_code == 200
    assert "section,key,value" in csv_resp.json()["csv"]

    packet = client.get("/alerts/weekly-brief/options/packet?max_chars=200")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "options" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_alerts_weekly_brief_all_options_endpoint():
    r = client.get("/alerts/weekly-brief/all/options")
    assert r.status_code == 200
    data = r.json()
    assert data["order_by"] == ["email", "total_alerts", "unread_alerts"]
    assert data["order_dir"] == ["asc", "desc"]
    assert data["defaults"]["days"] == 7
    assert data["constraints"]["min_total_alerts"]["max"] == 10000
    assert data["surfaces"]["all"] == "/alerts/weekly-brief/all"


def test_alerts_weekly_brief_all_options_export_endpoints():
    md = client.get("/alerts/weekly-brief/all/options/markdown")
    assert md.status_code == 200
    assert "# Weekly Brief All Options" in md.json()["markdown"]

    tg = client.get("/alerts/weekly-brief/all/options/telegram?max_chars=200")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get("/alerts/weekly-brief/all/options/csv")
    assert csv_resp.status_code == 200
    assert "section,key,value" in csv_resp.json()["csv"]

    packet = client.get("/alerts/weekly-brief/all/options/packet?max_chars=200")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "options" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_alerts_weekly_brief_all_and_summary_endpoints():
    email_a = f"weeklybrief-all-a-{uuid4().hex[:8]}@example.com"
    email_b = f"weeklybrief-all-b-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email_a, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email_b, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("orangetheory", ["litigation"], risk_level="medium")

    all_resp = client.get(
        "/alerts/weekly-brief/all?days=7&max_alerts=200&order_by=total_alerts&order_dir=desc&limit=1&offset=0"
    )
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert all_data["emails_scanned"] >= 2
    assert all_data["matched"] >= 2
    assert all_data["returned"] == 1
    assert all_data["order_by"] == "total_alerts"
    assert all_data["order_dir"] == "desc"
    assert "has_more" in all_data
    assert isinstance(all_data["briefs"], list)

    summary_resp = client.get(
        "/alerts/weekly-brief/all/summary?days=7&max_alerts=200&unread_only=true&min_total_alerts=1&top_n=1"
    )
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["unread_only"] is True
    assert summary_data["min_total_alerts"] == 1
    assert summary_data["top_n"] == 1
    assert "total_alerts" in summary_data
    assert "unread_alert_total" in summary_data
    assert len(summary_data["top_unread_emails"]) <= 1


def test_alerts_weekly_brief_all_summary_export_endpoints():
    email = f"weeklybrief-all-summary-export-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get(
        "/alerts/weekly-brief/all/summary/markdown?days=7&max_alerts=200&limit=10&offset=0&top_n=5"
    )
    assert md.status_code == 200
    assert "Weekly Brief All-Email Summary" in md.json()["markdown"]

    tg = client.get(
        "/alerts/weekly-brief/all/summary/telegram?days=7&max_alerts=200&limit=10&offset=0&top_n=5&max_chars=200"
    )
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get("/alerts/weekly-brief/all/summary/csv?days=7&max_alerts=200&top_n=5")
    assert csv_resp.status_code == 200
    assert "emails_scanned,matched,returned,limit,offset,page_end" in csv_resp.json()["csv"]

    packet = client.get(
        "/alerts/weekly-brief/all/summary/packet?days=7&max_alerts=200&limit=10&offset=0&top_n=5&max_chars=200"
    )
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "summary" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data


def test_alerts_weekly_brief_all_export_endpoints():
    email = f"weeklybrief-all-export-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get("/alerts/weekly-brief/all/markdown?days=7&max_alerts=200&limit=1&offset=0")
    assert md.status_code == 200
    assert "Weekly Brief All Emails" in md.json()["markdown"]

    tg = client.get("/alerts/weekly-brief/all/telegram?days=7&max_alerts=200&limit=1&offset=0&max_chars=200")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["chunk_count"] >= 1
    assert tg_data["chunks_with_index"][0].startswith("[1/")

    csv_resp = client.get("/alerts/weekly-brief/all/csv?days=7&max_alerts=200&limit=1&offset=0")
    assert csv_resp.status_code == 200
    assert "emails_scanned,matched,returned,limit,offset,page_end" in csv_resp.json()["csv"]

    packet = client.get("/alerts/weekly-brief/all/packet?days=7&max_alerts=200&limit=1&offset=0&max_chars=200")
    assert packet.status_code == 200
    packet_data = packet.json()
    assert "payload" in packet_data
    assert "markdown" in packet_data
    assert "csv" in packet_data
    assert "telegram" in packet_data



def test_alerts_digest_run_for_email():
    email = f"digest-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": True, "run_id": "api-run-1"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert data["sent"] is True
    assert data["marked_read"] >= 1
    assert data["run_id"] == "api-run-1"


def test_alerts_digest_run_for_all_watchlist_emails():
    email_a = f"digestall-a-{uuid4().hex[:8]}@example.com"
    email_b = f"digestall-b-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email_a, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email_b, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    seed_change_summary("orangetheory", ["litigation"], risk_level="medium")

    r = client.post("/alerts/digest/run", json={"max_alerts": 5, "mark_read": False})
    assert r.status_code == 200
    data = r.json()
    assert data["emails_scanned"] >= 2
    assert data["digests_sent"] >= 2
    assert "run_id" in data
    assert isinstance(data["results"], list)


def test_alerts_digest_preview_endpoint_with_unread_alerts():
    email = f"digestpreview-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/digest/preview?email={email}&max_alerts=10")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert data["has_unread"] is True
    assert data["unread_count"] >= 1
    assert "FDD Tracker:" in data["subject"]
    assert isinstance(data["alerts"], list)
    assert len(data["alerts"]) >= 1


def test_alerts_digest_preview_endpoint_when_empty():
    email = f"digestpreview-empty-{uuid4().hex[:8]}@example.com"
    r = client.get(f"/alerts/digest/preview?email={email}&max_alerts=10")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert data["has_unread"] is False
    assert data["unread_count"] == 0
    assert data["subject"] is None
    assert data["body"] is None
    assert data["alerts"] == []


def test_alerts_digest_preview_markdown_endpoint():
    email = f"digestpreview-md-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/digest/preview/markdown?email={email}&max_alerts=10")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert "markdown" in data
    assert "# Digest Preview" in data["markdown"]


def test_alerts_digest_preview_telegram_endpoint():
    email = f"digestpreview-tg-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/digest/preview/telegram?email={email}&max_alerts=10&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert data["chunk_count"] >= 1
    assert data["chunks_with_index"][0].startswith("[1/")


def test_alerts_digest_preview_csv_endpoint():
    email = f"digestpreview-csv-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/digest/preview/csv?email={email}&max_alerts=10")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert "csv" in data
    assert "email,has_unread,unread_count" in data["csv"]


def test_alerts_digest_preview_packet_endpoint():
    email = f"digestpreview-packet-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get(f"/alerts/digest/preview/packet?email={email}&max_alerts=10&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == email
    assert "preview" in data
    assert "markdown" in data
    assert "csv" in data
    assert "telegram" in data and data["telegram"]["chunk_count"] >= 1


def test_alerts_digest_preview_all_options_endpoint():
    r = client.get("/alerts/digest/preview/all/options")
    assert r.status_code == 200
    data = r.json()
    assert data["order_by"] == ["email", "unread_count", "has_unread", "generated_at"]
    assert data["order_dir"] == ["asc", "desc"]
    assert data["constraints"]["limit"]["type"] == "int|null"
    assert data["constraints"]["max_chars"]["max"] == 10000
    assert data["defaults"]["order_by"] == "email"
    assert data["defaults"]["order_dir"] == "asc"
    assert data["defaults"]["max_chars"] == 2500
    assert data["surfaces"]["preview"] == "/alerts/digest/preview/all"


def test_alerts_digest_preview_options_endpoint():
    r = client.get("/alerts/digest/preview/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["email"]["required"] is True
    assert data["constraints"]["max_chars"]["min"] == 200
    assert data["defaults"]["max_alerts"] == 25
    assert data["surfaces"]["preview"] == "/alerts/digest/preview"


def test_alerts_digest_run_options_endpoint():
    r = client.get("/alerts/digest/run/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["max_alerts"]["max"] == 200
    assert data["defaults"]["max_alerts"] == 25
    assert data["defaults"]["mark_read"] is False
    assert "all_emails" in data["modes"]
    assert data["surfaces"]["run"] == "/alerts/digest/run"


def test_alerts_cron_options_endpoint():
    r = client.get("/alerts/cron/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["dispatch_limit"]["max"] == 500
    assert "noop" in data["constraints"]["dispatch_provider"]["enum"]
    assert data["defaults"]["dispatch_provider"] == "noop"
    assert data["defaults"]["lock_stale_after_seconds"] == 900
    assert data["providers"]["default"] == "noop"
    assert "resend" in data["providers"]["live_capable"]
    assert "noop" in data["providers"]["health"]
    assert data["providers"]["health"]["noop"]["ready"] is True
    assert data["surfaces"]["options"] == "/alerts/cron/options"
    assert data["surfaces"]["tick"] == "/alerts/cron/tick"


def test_alerts_outbox_dispatch_options_endpoint():
    r = client.get("/alerts/outbox/dispatch/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["limit"]["max"] == 500
    assert "noop" in data["constraints"]["provider"]["enum"]
    assert data["defaults"]["provider"] == "noop"
    assert data["live_dispatch_gate"]["requires_confirm_live"] is True
    assert data["providers"]["default"] == "noop"
    assert "resend" in data["providers"]["live_capable"]
    assert data["surfaces"]["options"] == "/alerts/outbox/dispatch/options"


def test_alerts_outbox_retry_failed_options_endpoint():
    r = client.get("/alerts/outbox/retry-failed/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["limit"]["max"] == 500
    assert data["defaults"]["limit"] == 100
    assert data["surfaces"]["options"] == "/alerts/outbox/retry-failed/options"
    assert data["surfaces"]["retry_failed"] == "/alerts/outbox/retry-failed"


def test_alerts_retention_prune_options_endpoint():
    r = client.get("/alerts/retention/prune/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["outbox_keep_last"]["min"] == 0
    assert data["constraints"]["sent_keep_last"]["max"] == 50000
    assert data["defaults"]["failed_keep_last"] == 1000
    assert data["defaults"]["history_keep_last"] == 2000
    assert data["surfaces"]["options"] == "/alerts/retention/prune/options"
    assert data["surfaces"]["prune"] == "/alerts/retention/prune"


def test_alerts_cron_history_options_endpoint():
    r = client.get("/alerts/cron/history/options")
    assert r.status_code == 200
    data = r.json()
    assert data["constraints"]["limit"]["min"] == 1
    assert data["constraints"]["limit"]["max"] == 500
    assert data["defaults"]["limit"] == 50
    assert data["surfaces"]["options"] == "/alerts/cron/history/options"
    assert data["surfaces"]["latest"] == "/alerts/cron/history/latest"


def test_alerts_digest_preview_all_endpoint():
    email_a = f"digestpreview-all-a-{uuid4().hex[:8]}@example.com"
    email_b = f"digestpreview-all-b-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email_a, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email_b, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get("/alerts/digest/preview/all?max_alerts=10&order_by=unread_count&order_dir=desc&limit=1&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["emails_scanned"] >= 2
    assert data["matched"] >= 2
    assert data["returned"] == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert "has_more" in data
    assert "next_offset" in data
    assert "prev_offset" in data
    assert "effective_limit" in data
    assert "current_page" in data
    assert "total_pages" in data
    assert data["order_by"] == "unread_count"
    assert data["order_dir"] == "desc"
    assert isinstance(data["previews"], list)

    r2 = client.get("/alerts/digest/preview/all?max_alerts=10&unread_only=true")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["unread_only"] is True

    r3 = client.get("/alerts/digest/preview/all?max_alerts=10&min_unread=1")
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["min_unread"] == 1
    assert all(int(item.get("unread_count") or 0) >= 1 for item in data3["previews"])


def test_alerts_digest_preview_all_markdown_telegram_csv_packet_endpoints():
    email = f"digestpreview-all-view-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get("/alerts/digest/preview/all/markdown?max_alerts=10&min_unread=1&order_by=email&order_dir=asc&limit=1&offset=0")
    assert md.status_code == 200
    assert "markdown" in md.json()
    assert "Digest Preview All Emails" in md.json()["markdown"]
    assert "Min unread filter: 1" in md.json()["markdown"]
    assert "Pagination: limit=1 offset=0" in md.json()["markdown"]
    assert "Ordering: email asc" in md.json()["markdown"]

    tg = client.get("/alerts/digest/preview/all/telegram?max_alerts=10&min_unread=1&limit=1&offset=0&max_chars=200")
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd["min_unread"] == 1
    assert tgd["limit"] == 1
    assert tgd["offset"] == 0
    assert "has_more" in tgd
    assert "next_offset" in tgd
    assert "prev_offset" in tgd
    assert "effective_limit" in tgd
    assert "current_page" in tgd
    assert "total_pages" in tgd
    assert "order_by" in tgd
    assert "order_dir" in tgd
    assert tgd["chunk_count"] >= 1
    assert tgd["chunks_with_index"][0].startswith("[1/")

    csv_r = client.get("/alerts/digest/preview/all/csv?max_alerts=10&min_unread=1&limit=1&offset=0")
    assert csv_r.status_code == 200
    assert "csv" in csv_r.json()
    assert "emails_scanned,matched,returned,limit,offset,page_end,has_more,next_offset,prev_offset,effective_limit,current_page,total_pages,order_by,order_dir,unread_only,min_unread,email,has_unread" in csv_r.json()["csv"]

    packet_r = client.get("/alerts/digest/preview/all/packet?max_alerts=10&min_unread=1&limit=1&offset=0&max_chars=200")
    assert packet_r.status_code == 200
    pkt = packet_r.json()
    assert "payload" in pkt
    assert pkt["payload"]["min_unread"] == 1
    assert pkt["payload"]["limit"] == 1
    assert "markdown" in pkt
    assert "csv" in pkt
    assert "telegram" in pkt
    assert pkt["telegram"]["chunk_count"] >= 1


def test_alerts_digest_preview_all_summary_endpoint():
    email_a = f"digestpreview-allsum-a-{uuid4().hex[:8]}@example.com"
    email_b = f"digestpreview-allsum-b-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email_a, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email_b, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get("/alerts/digest/preview/all/summary?max_alerts=10&min_unread=1&limit=1&offset=0&top_n=1")
    assert r.status_code == 200
    data = r.json()
    assert data["emails_scanned"] >= 2
    assert data["matched"] >= 1
    assert data["min_unread"] == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert "has_more" in data
    assert "next_offset" in data
    assert "prev_offset" in data
    assert "effective_limit" in data
    assert "current_page" in data
    assert "total_pages" in data
    assert data["order_by"] == "email"
    assert data["order_dir"] == "asc"
    assert data["top_n"] == 1
    assert len(data["top_unread_emails"]) <= 1
    assert "unread_alert_total" in data
    assert "top_unread_emails" in data and isinstance(data["top_unread_emails"], list)


def test_alerts_digest_preview_all_summary_markdown_and_telegram_endpoints():
    email = f"digestpreview-allsum-view-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get("/alerts/digest/preview/all/summary/markdown?max_alerts=10&min_unread=1&limit=1&offset=0&top_n=1")
    assert md.status_code == 200
    assert "markdown" in md.json()
    assert "Digest Preview All-Email Summary" in md.json()["markdown"]
    assert "Min unread filter: 1" in md.json()["markdown"]
    assert "Pagination: limit=1 offset=0" in md.json()["markdown"]
    assert "Top Unread Emails (1)" in md.json()["markdown"]

    tg = client.get("/alerts/digest/preview/all/summary/telegram?max_alerts=10&min_unread=1&limit=1&offset=0&top_n=1&max_chars=200")
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd["min_unread"] == 1
    assert tgd["limit"] == 1
    assert tgd["offset"] == 0
    assert "has_more" in tgd
    assert "next_offset" in tgd
    assert "prev_offset" in tgd
    assert "effective_limit" in tgd
    assert "current_page" in tgd
    assert "total_pages" in tgd
    assert "order_by" in tgd
    assert "order_dir" in tgd
    assert tgd["top_n"] == 1
    assert tgd["chunk_count"] >= 1
    assert tgd["chunks_with_index"][0].startswith("[1/")


def test_alerts_digest_preview_all_summary_csv_and_packet_endpoints():
    email = f"digestpreview-allsum-packet-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    csv_r = client.get("/alerts/digest/preview/all/summary/csv?max_alerts=10&min_unread=1&limit=1&offset=0&top_n=1")
    assert csv_r.status_code == 200
    assert "csv" in csv_r.json()
    assert "top_n" in csv_r.json()["csv"]

    packet_r = client.get("/alerts/digest/preview/all/summary/packet?max_alerts=10&min_unread=1&limit=1&offset=0&top_n=1&max_chars=200")
    assert packet_r.status_code == 200
    pkt = packet_r.json()
    assert "summary" in pkt
    assert pkt["summary"]["min_unread"] == 1
    assert pkt["summary"]["limit"] == 1
    assert pkt["summary"]["top_n"] == 1
    assert "markdown" in pkt
    assert "csv" in pkt
    assert "telegram" in pkt
    assert pkt["telegram"]["chunk_count"] >= 1



def test_alerts_outbox_endpoints():
    email = f"outbox-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    run = client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": False})
    assert run.status_code == 200
    assert run.json()["sent"] is True

    outbox = client.get("/alerts/outbox?limit=10")
    assert outbox.status_code == 200
    assert isinstance(outbox.json()["items"], list)

    dispatched = client.post("/alerts/outbox/dispatch", json={"limit": 10})
    assert dispatched.status_code == 200
    assert "dispatched" in dispatched.json()
    assert "remaining" in dispatched.json()



def test_alerts_outbox_retry_failed_endpoint():
    r = client.post("/alerts/outbox/retry-failed", json={"limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert "retried" in data
    assert "remaining_failed" in data



def test_alerts_cron_tick_endpoint():
    email = f"crontick-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": "api-cron-run",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == "api-cron-run"
    assert "generated" in data
    assert "dispatched" in data
    assert "retried" in data
    assert data["dispatched"]["provider"] == "noop"
    assert data["dispatched"]["dry_run"] is True



def test_alerts_cron_history_endpoint():
    r = client.get("/alerts/cron/history?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)



def test_alerts_retention_prune_endpoint():
    r = client.post(
        "/alerts/retention/prune",
        json={
            "outbox_keep_last": 10,
            "sent_keep_last": 10,
            "failed_keep_last": 10,
            "history_keep_last": 10,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "outbox" in data
    assert "sent" in data
    assert "failed" in data
    assert "history" in data


def test_alerts_cron_tick_endpoint_skips_when_locked(tmp_path, monkeypatch):
    lock = tmp_path / "alerts_cron.lock"
    lock.write_text('{"run_id":"active-api-run","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding="utf-8")

    from app import main as main_module

    original = main_module.run_alerts_cron_tick

    def wrapped(*args, **kwargs):
        kwargs["lock_path"] = str(lock)
        return original(*args, **kwargs)

    monkeypatch.setattr(main_module, "run_alerts_cron_tick", wrapped)

    r = client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "run_id": "api-cron-locked-run",
            "lock_stale_after_seconds": 900,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "skipped_locked"
    assert data["lock"]["acquired"] is False


def test_alerts_outbox_dispatch_with_provider_metadata():
    email = f"outboxmeta-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": False})

    dispatched = client.post("/alerts/outbox/dispatch", json={"limit": 10, "dry_run": True, "provider": "noop"})
    assert dispatched.status_code == 200
    data = dispatched.json()
    assert "dry_run" in data and data["dry_run"] is True
    assert data["provider"] == "noop"
    assert 'validation' in data


def test_alerts_providers_endpoint():
    r = client.get('/alerts/providers')
    assert r.status_code == 200
    data = r.json()
    assert data['default'] == 'noop'
    assert 'providers' in data
    assert 'noop' in data['providers']


def test_alerts_providers_health_endpoint():
    r = client.get('/alerts/providers/health')
    assert r.status_code == 200
    data = r.json()
    assert sorted(data['requested']) == sorted(data['supported'])
    assert 'noop' in data['supported']
    assert any(item['provider'] == 'noop' for item in data['items'])


def test_alerts_providers_health_endpoint_with_filter():
    r = client.get('/alerts/providers/health', params={'provider': 'noop'})
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['noop']
    assert len(data['items']) == 1
    assert data['items'][0]['provider'] == 'noop'


def test_alerts_providers_health_options_endpoint():
    r = client.get('/alerts/providers/health/options')
    assert r.status_code == 200
    data = r.json()
    assert data['constraints']['provider']['type'] == 'string|null'
    assert data['defaults']['provider'] is None
    assert data['surfaces']['health'] == '/alerts/providers/health'


def test_alerts_outbox_dispatch_rejects_unknown_provider():
    r = client.post('/alerts/outbox/dispatch', json={'limit': 10, 'provider': 'not-real', 'dry_run': True})
    assert r.status_code == 200
    data = r.json()
    assert data['dispatched'] == 0
    assert data['error']['reason'] == 'unsupported-provider'
    assert data['remaining'] >= 0


def test_alerts_cron_status_endpoint():
    r = client.get('/alerts/cron/status?lock_stale_after_seconds=900')
    assert r.status_code == 200
    data = r.json()
    assert 'counts' in data
    assert 'lock' in data
    assert 'paths' in data


def test_alerts_cron_recover_lock_endpoint():
    r = client.post('/alerts/cron/recover-lock', json={'lock_stale_after_seconds': 900, 'force': False})
    assert r.status_code == 200
    data = r.json()
    assert 'recovered' in data
    assert 'reason' in data


def test_alerts_cron_preflight_endpoint():
    r = client.post('/alerts/cron/preflight', json={'dispatch_dry_run': True, 'dispatch_provider': 'noop', 'lock_stale_after_seconds': 900})
    assert r.status_code == 200
    data = r.json()
    assert 'ready_to_run' in data
    assert 'dispatch' in data
    assert 'lock' in data
    assert data['dispatch']['validation']['ok'] is True
    assert data['dispatch']['requested_provider'] == 'noop'
    assert data['dispatch']['effective_provider'] == 'noop'
    assert data['dispatch']['provider_health']['provider'] == 'noop'


def test_alerts_cron_history_latest_endpoint():
    r = client.get('/alerts/cron/history/latest')
    assert r.status_code == 200
    data = r.json()
    assert 'exists' in data
    assert 'item' in data


def test_alerts_provider_smoke_test_options_endpoint():
    r = client.get('/alerts/providers/smoke-test/options')
    assert r.status_code == 200
    data = r.json()
    assert 'noop' in data['constraints']['provider']['enum']
    assert data['constraints']['email']['format'] == 'email'
    assert data['defaults']['provider'] == 'noop'
    assert data['providers']['default'] == 'noop'
    assert data['surfaces']['options'] == '/alerts/providers/smoke-test/options'


def test_alerts_providers_options_endpoint():
    r = client.get('/alerts/providers/options')
    assert r.status_code == 200
    data = r.json()
    assert data['defaults']['provider'] == 'noop'
    assert data['constraints']['query'] is None
    assert 'noop' in data['providers']['supported']
    assert 'health' in data['providers']
    assert data['surfaces']['options'] == '/alerts/providers/options'
    assert data['surfaces']['options_markdown'] == '/alerts/providers/options/markdown'
    assert data['surfaces']['options_telegram'] == '/alerts/providers/options/telegram'
    assert data['surfaces']['options_csv'] == '/alerts/providers/options/csv'
    assert data['surfaces']['options_packet'] == '/alerts/providers/options/packet'
    assert data['surfaces']['health_options'] == '/alerts/providers/health/options'
    assert data['surfaces']['health_details'] == '/alerts/providers/{provider}/health'


def test_alerts_providers_options_presentation_endpoints():
    md = client.get('/alerts/providers/options/markdown')
    assert md.status_code == 200
    assert '# Provider Catalog Options' in md.json()['markdown']

    tg = client.get('/alerts/providers/options/telegram?max_chars=200')
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd['chunk_count'] >= 1
    assert tgd['chunks_with_index'][0].startswith('[1/')

    csv_res = client.get('/alerts/providers/options/csv')
    assert csv_res.status_code == 200
    assert 'section,key,value' in csv_res.json()['csv']

    packet = client.get('/alerts/providers/options/packet?max_chars=200')
    assert packet.status_code == 200
    data = packet.json()
    assert 'options' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data


def test_alerts_providers_health_endpoint_defaults():
    r = client.get('/alerts/providers/health')
    assert r.status_code == 200
    data = r.json()
    assert 'supported' in data
    assert isinstance(data['items'], list)
    assert any(item['provider'] == 'noop' for item in data['items'])


def test_alerts_providers_health_endpoint_with_filter():
    r = client.get('/alerts/providers/health?provider=resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['resend', 'not-real']
    assert data['items'][0]['provider'] == 'resend'
    assert data['items'][1]['known'] is False


def test_alerts_providers_health_summary_endpoint():
    r = client.get('/alerts/providers/health/summary?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['counts']['total'] == 3
    assert data['counts']['known'] == 2
    assert data['counts']['unknown'] == 1
    assert 'items' in data and len(data['items']) == 3


def test_alerts_providers_health_summary_options_endpoint():
    r = client.get('/alerts/providers/health/summary/options')
    assert r.status_code == 200
    data = r.json()
    assert data['constraints']['provider']['type'] == 'csv|string|null'
    assert data['constraints']['max_chars']['minimum'] == 100
    assert data['surfaces']['options'] == '/alerts/providers/health/summary/options'
    assert data['surfaces']['options_markdown'] == '/alerts/providers/health/summary/options/markdown'
    assert data['surfaces']['options_telegram'] == '/alerts/providers/health/summary/options/telegram'
    assert data['surfaces']['options_csv'] == '/alerts/providers/health/summary/options/csv'
    assert data['surfaces']['options_packet'] == '/alerts/providers/health/summary/options/packet'
    assert data['surfaces']['packet'] == '/alerts/providers/health/summary/packet'


def test_alerts_providers_health_summary_options_presentation_endpoints():
    md = client.get('/alerts/providers/health/summary/options/markdown')
    assert md.status_code == 200
    assert '# Provider Health Summary Options' in md.json()['markdown']

    tg = client.get('/alerts/providers/health/summary/options/telegram?max_chars=200')
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd['chunk_count'] >= 1
    assert tgd['chunks_with_index'][0].startswith('[1/')

    csv_res = client.get('/alerts/providers/health/summary/options/csv')
    assert csv_res.status_code == 200
    assert 'section,key,value' in csv_res.json()['csv']

    packet = client.get('/alerts/providers/health/summary/options/packet?max_chars=200')
    assert packet.status_code == 200
    data = packet.json()
    assert 'options' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data
    assert data['telegram']['chunk_count'] >= 1


def test_alerts_providers_health_summary_recommendations_endpoint():
    r = client.get('/alerts/providers/health/summary/recommendations?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['recommendation_count'] >= 1
    assert any(row.get('code') == 'unknown-providers-requested' for row in data['recommendations'])


def test_alerts_providers_health_summary_recommendations_markdown_endpoint():
    r = client.get('/alerts/providers/health/summary/recommendations/markdown?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['noop', 'resend', 'not-real']
    assert '# Provider Health Recommendations' in data['markdown']


def test_alerts_providers_health_summary_recommendations_telegram_endpoint():
    r = client.get('/alerts/providers/health/summary/recommendations/telegram?provider=noop,resend,not-real&max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert data['chunk_count'] >= 1
    assert data['chunks_with_index'][0].startswith('[1/')


def test_alerts_providers_health_summary_recommendations_csv_endpoint():
    r = client.get('/alerts/providers/health/summary/recommendations/csv?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['noop', 'resend', 'not-real']
    assert 'metric,value' in data['csv']
    assert 'severity,code,message,action,env_key,count,providers,supported' in data['csv']


def test_alerts_providers_health_summary_recommendations_packet_endpoint():
    r = client.get('/alerts/providers/health/summary/recommendations/packet?provider=noop,resend,not-real&max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert 'recommendations' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data
    assert data['telegram']['chunk_count'] >= 1


def test_alerts_providers_health_summary_markdown_endpoint():
    r = client.get('/alerts/providers/health/summary/markdown?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['noop', 'resend', 'not-real']
    assert '# Provider Health Summary' in data['markdown']


def test_alerts_providers_health_summary_telegram_endpoint():
    r = client.get('/alerts/providers/health/summary/telegram?provider=noop,resend,not-real&max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert data['chunk_count'] >= 1
    assert len(data['chunks']) == data['chunk_count']
    assert data['chunks_with_index'][0].startswith('[1/')


def test_alerts_providers_health_summary_csv_endpoint():
    r = client.get('/alerts/providers/health/summary/csv?provider=noop,resend,not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['requested'] == ['noop', 'resend', 'not-real']
    assert 'metric,value' in data['csv']
    assert 'provider,known,ready,supports_live,missing_env' in data['csv']


def test_alerts_providers_health_summary_packet_endpoint():
    r = client.get('/alerts/providers/health/summary/packet?provider=noop,resend,not-real&max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert 'summary' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data
    assert data['telegram']['chunk_count'] >= 1


def test_alerts_providers_health_options_endpoint():
    r = client.get('/alerts/providers/health/options')
    assert r.status_code == 200
    data = r.json()
    assert data['defaults']['provider'] is None
    assert 'noop' in data['providers']['supported']
    assert data['constraints']['provider']['type'] == 'csv|string|null'
    assert data['constraints']['max_chars']['minimum'] == 100
    assert data['defaults']['max_chars'] == 3500
    assert data['surfaces']['options'] == '/alerts/providers/health/options'
    assert data['surfaces']['options_markdown'] == '/alerts/providers/health/options/markdown'
    assert data['surfaces']['options_telegram'] == '/alerts/providers/health/options/telegram'
    assert data['surfaces']['options_csv'] == '/alerts/providers/health/options/csv'
    assert data['surfaces']['options_packet'] == '/alerts/providers/health/options/packet'
    assert data['surfaces']['health_summary'] == '/alerts/providers/health/summary'
    assert data['surfaces']['health_summary_options'] == '/alerts/providers/health/summary/options'
    assert data['surfaces']['health_summary_recommendations'] == '/alerts/providers/health/summary/recommendations'
    assert data['surfaces']['health_summary_recommendations_csv'] == '/alerts/providers/health/summary/recommendations/csv'
    assert data['surfaces']['health_summary_recommendations_packet'] == '/alerts/providers/health/summary/recommendations/packet'


def test_alerts_providers_health_options_presentation_endpoints():
    md = client.get('/alerts/providers/health/options/markdown')
    assert md.status_code == 200
    assert '# Provider Health Options' in md.json()['markdown']

    tg = client.get('/alerts/providers/health/options/telegram?max_chars=200')
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd['chunk_count'] >= 1
    assert tgd['chunks_with_index'][0].startswith('[1/')

    csv_res = client.get('/alerts/providers/health/options/csv')
    assert csv_res.status_code == 200
    assert 'section,key,value' in csv_res.json()['csv']

    packet = client.get('/alerts/providers/health/options/packet?max_chars=200')
    assert packet.status_code == 200
    data = packet.json()
    assert 'options' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data


def test_alerts_provider_details_endpoint_supported():
    r = client.get('/alerts/providers/noop')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'noop'
    assert data['supported'] is True
    assert data['health']['provider'] == 'noop'
    assert data['validation']['dry_run']['ok'] is True


def test_alerts_provider_details_endpoint_unknown():
    r = client.get('/alerts/providers/not-real')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'not-real'
    assert data['supported'] is False
    assert data['health']['known'] is False
    assert data['validation']['dry_run']['ok'] is False


def test_alerts_provider_details_options_endpoint():
    r = client.get('/alerts/providers/details/options')
    assert r.status_code == 200
    data = r.json()
    assert data['defaults']['provider'] == 'noop'
    assert 'noop' in data['providers']['supported']
    assert data['constraints']['provider']['path_param'] is True
    assert data['surfaces']['options'] == '/alerts/providers/details/options'
    assert data['surfaces']['options_markdown'] == '/alerts/providers/details/options/markdown'
    assert data['surfaces']['options_telegram'] == '/alerts/providers/details/options/telegram'
    assert data['surfaces']['options_csv'] == '/alerts/providers/details/options/csv'
    assert data['surfaces']['options_packet'] == '/alerts/providers/details/options/packet'
    assert data['surfaces']['health_options'] == '/alerts/providers/health/options'
    assert data['surfaces']['health_details'] == '/alerts/providers/{provider}/health'


def test_alerts_provider_details_options_presentation_endpoints():
    md = client.get('/alerts/providers/details/options/markdown')
    assert md.status_code == 200
    assert '# Provider Details Options' in md.json()['markdown']

    tg = client.get('/alerts/providers/details/options/telegram?max_chars=200')
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd['chunk_count'] >= 1
    assert tgd['chunks_with_index'][0].startswith('[1/')

    csv_res = client.get('/alerts/providers/details/options/csv')
    assert csv_res.status_code == 200
    assert 'section,key,value' in csv_res.json()['csv']

    packet = client.get('/alerts/providers/details/options/packet?max_chars=200')
    assert packet.status_code == 200
    data = packet.json()
    assert 'options' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data
    assert data['telegram']['chunk_count'] >= 1


def test_alerts_provider_health_details_endpoint_supported():
    r = client.get('/alerts/providers/noop/health')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'noop'
    assert data['supported'] is True
    assert data['health']['known'] is True


def test_alerts_provider_health_details_endpoint_unknown():
    r = client.get('/alerts/providers/not-real/health')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'not-real'
    assert data['supported'] is False
    assert data['health']['known'] is False


def test_alerts_provider_recommendations_endpoint_supported():
    r = client.get('/alerts/providers/noop/recommendations')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'noop'
    assert isinstance(data['actions'], list)
    assert any(item['code'] == 'run-smoke-test' for item in data['actions'])


def test_alerts_provider_recommendations_markdown_endpoint():
    r = client.get('/alerts/providers/noop/recommendations/markdown')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'noop'
    assert '# Provider Recommendations' in data['markdown']


def test_alerts_provider_recommendations_telegram_endpoint():
    r = client.get('/alerts/providers/noop/recommendations/telegram?max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert data['chunk_count'] >= 1
    assert data['chunks_with_index'][0].startswith('[1/')


def test_alerts_provider_recommendations_csv_endpoint():
    r = client.get('/alerts/providers/noop/recommendations/csv')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'noop'
    assert 'metric,value' in data['csv']
    assert 'priority,code,message,reason,missing_env,supported_providers,endpoint' in data['csv']


def test_alerts_provider_recommendations_packet_endpoint():
    r = client.get('/alerts/providers/noop/recommendations/packet?max_chars=220')
    assert r.status_code == 200
    data = r.json()
    assert 'recommendations' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data


def test_alerts_provider_recommendations_endpoint_unknown():
    r = client.get('/alerts/providers/not-real/recommendations')
    assert r.status_code == 200
    data = r.json()
    assert data['provider'] == 'not-real'
    assert data['ready_for_live_dispatch'] is False
    assert any(item['code'] == 'choose-supported-provider' for item in data['actions'])


def test_alerts_provider_recommendations_options_endpoint():
    r = client.get('/alerts/providers/recommendations/options')
    assert r.status_code == 200
    data = r.json()
    assert data['defaults']['provider'] == 'noop'
    assert data['defaults']['max_chars'] == 3500
    assert 'noop' in data['providers']['supported']
    assert isinstance(data['providers']['live_capable'], list)
    assert isinstance(data['providers']['ready'], list)
    assert data['providers']['health']['noop']['provider'] == 'noop'
    assert data['providers']['health']['noop']['supported'] is True
    assert data['providers']['health']['noop']['health']['known'] is True
    assert data['constraints']['provider']['path_param'] is True
    assert data['constraints']['max_chars']['minimum'] == 100
    assert data['constraints']['max_chars']['maximum'] == 4096
    assert data['surfaces']['options'] == '/alerts/providers/recommendations/options'
    assert data['surfaces']['options_markdown'] == '/alerts/providers/recommendations/options/markdown'
    assert data['surfaces']['options_telegram'] == '/alerts/providers/recommendations/options/telegram'
    assert data['surfaces']['options_csv'] == '/alerts/providers/recommendations/options/csv'
    assert data['surfaces']['options_packet'] == '/alerts/providers/recommendations/options/packet'
    assert data['surfaces']['details_options'] == '/alerts/providers/details/options'
    assert data['surfaces']['recommendations_markdown'] == '/alerts/providers/{provider}/recommendations/markdown'
    assert data['surfaces']['recommendations_telegram'] == '/alerts/providers/{provider}/recommendations/telegram'
    assert data['surfaces']['recommendations_csv'] == '/alerts/providers/{provider}/recommendations/csv'
    assert data['surfaces']['recommendations_packet'] == '/alerts/providers/{provider}/recommendations/packet'
    assert data['surfaces']['health_options'] == '/alerts/providers/health/options'


def test_alerts_provider_recommendations_options_presentation_endpoints():
    md = client.get('/alerts/providers/recommendations/options/markdown')
    assert md.status_code == 200
    assert '# Provider Recommendations Options' in md.json()['markdown']

    tg = client.get('/alerts/providers/recommendations/options/telegram?max_chars=200')
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd['chunk_count'] >= 1
    assert tgd['chunks_with_index'][0].startswith('[1/')

    csv_res = client.get('/alerts/providers/recommendations/options/csv')
    assert csv_res.status_code == 200
    assert 'section,key,value' in csv_res.json()['csv']

    packet = client.get('/alerts/providers/recommendations/options/packet?max_chars=200')
    assert packet.status_code == 200
    data = packet.json()
    assert 'options' in data
    assert 'markdown' in data
    assert 'csv' in data
    assert 'telegram' in data
    assert data['telegram']['chunk_count'] >= 1


def test_alerts_provider_smoke_test_dry_run():
    r = client.post('/alerts/providers/smoke-test', json={'provider': 'noop', 'email': 'smoke@example.com', 'dry_run': True})
    assert r.status_code == 200
    data = r.json()
    assert data['success'] is True
    assert data['provider'] == 'noop'
    assert data['mode'] == 'dry_run'
    assert data['email'] == 'smoke@example.com'
    assert 'provider_message_id' in data


def test_alerts_outbox_dispatch_live_requires_confirmation():
    r = client.post('/alerts/outbox/dispatch', json={'limit': 10, 'provider': 'resend', 'dry_run': False})
    assert r.status_code == 200
    data = r.json()
    assert data['dispatched'] == 0
    assert data['error']['reason'] == 'live-dispatch-confirmation-required'



def test_alerts_outbox_dispatch_live_duplicate_idempotency_key_rejected():
    payload = {
        'limit': 1,
        'provider': 'resend',
        'dry_run': False,
        'confirm_live': True,
        'idempotency_key': 'dup-key-1',
        'live_min_interval_seconds': 1,
    }
    first = client.post('/alerts/outbox/dispatch', json=payload)
    assert first.status_code == 200

    second = client.post('/alerts/outbox/dispatch', json=payload)
    assert second.status_code == 200
    data = second.json()
    assert data['dispatched'] == 0
    assert data['error']['reason'] == 'live-dispatch-duplicate-idempotency-key'


def test_alerts_cron_preflight_live_invalid_provider_fallback():
    r = client.post('/alerts/cron/preflight', json={'dispatch_dry_run': False, 'dispatch_provider': 'not-real', 'lock_stale_after_seconds': 900})
    assert r.status_code == 200
    data = r.json()
    assert data['dispatch']['fallback_applied'] is True
    assert data['dispatch']['effective_provider'] == 'noop'
    assert data['dispatch']['effective_dry_run'] is True
    assert data['dispatch']['validation']['ok'] is True


def test_alerts_outbox_sent_endpoint_filters_by_email_and_run_id():
    email = f"sent-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": False, "run_id": "api-sent-run"})
    client.post("/alerts/outbox/dispatch", json={"limit": 10, "dry_run": True, "provider": "noop"})

    r = client.get(f"/alerts/outbox/sent?email={email}&run_id=api-sent-run&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["items"], list)
    assert all(item.get("email") == email for item in data["items"])
    assert all(item.get("run_id") == "api-sent-run" for item in data["items"])


def test_alerts_outbox_failed_endpoint_filters():
    email = f"failed-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": False, "run_id": "api-failed-run"})

    # Force one failure by mutating outbox row directly via dispatch path expectation
    import json as _json
    from pathlib import Path as _Path
    from fdd_tracker.services.alerts import _default_data_path

    outbox = _Path(_default_data_path("alert_outbox.jsonl"))
    rows = [_json.loads(line) for line in outbox.read_text(encoding="utf-8").splitlines() if line.strip()]
    if rows:
        rows[-1]["force_fail"] = True
        outbox.write_text("\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    client.post("/alerts/outbox/dispatch", json={"limit": 10, "dry_run": True, "provider": "noop"})

    r = client.get(f"/alerts/outbox/failed?email={email}&run_id=api-failed-run&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["items"], list)
    assert all(item.get("email") == email for item in data["items"])
    assert all(item.get("run_id") == "api-failed-run" for item in data["items"])


def test_alerts_run_summary_endpoint():
    email = f"runsummary-{uuid4().hex[:8]}@example.com"
    run_id = "api-run-summary"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    client.post("/alerts/digest/run", json={"email": email, "max_alerts": 10, "mark_read": False, "run_id": run_id})
    client.post("/alerts/outbox/dispatch", json={"limit": 10, "dry_run": True, "provider": "noop"})

    r = client.get(f"/alerts/runs/{run_id}/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert data["exists"] is True
    assert "counts" in data and "latest" in data and "paths" in data and "operational" in data
    assert all(k in data["paths"] for k in ["outbox", "sent", "failed", "history"])
    assert all(k in data["operational"] for k in ["status", "degraded", "fallback_applied", "dispatch_validation_ok"])


def test_alerts_run_integrity_endpoint():
    email = f"runintegrity-{uuid4().hex[:8]}@example.com"
    run_id = "api-run-integrity"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get(f"/alerts/runs/{run_id}/integrity")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "ok" in data and "issues" in data and "summary" in data


def test_alerts_latest_run_integrity_endpoint():
    r = client.get("/alerts/runs/latest/integrity")
    assert r.status_code == 200
    data = r.json()
    assert "exists" in data
    assert "run_id" in data


def test_alerts_recent_runs_integrity_endpoint():
    email = f"recentintegrity-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": "api-recent-integrity-1",
        },
    )

    r = client.get("/alerts/runs/integrity?limit=5&status=executed")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "reports" in data
    assert isinstance(data["reports"], list)


def test_alerts_recent_runs_integrity_summary_endpoint():
    email = f"recentintegritysummary-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": "api-recent-integrity-summary",
        },
    )

    r = client.get("/alerts/runs/integrity/summary?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "ok_count" in data
    assert "failing_count" in data
    assert "failing_rate" in data
    assert "degraded_count" in data
    assert "degraded_rate" in data
    assert "issue_counts" in data
    assert "top_issues" in data


def test_alerts_recent_runs_integrity_failures_endpoint():
    r = client.get("/alerts/runs/integrity/failures?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "reports" in data
    assert isinstance(data["reports"], list)


def test_alerts_runs_integrity_dashboard_endpoint():
    r = client.get("/alerts/runs/integrity/dashboard?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "failures" in data
    assert "latest" in data


def test_alerts_runs_integrity_dashboard_markdown_endpoint():
    r = client.get("/alerts/runs/integrity/dashboard/markdown?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "markdown" in data
    assert "# Alert Integrity Dashboard" in data["markdown"]


def test_alerts_runs_integrity_dashboard_telegram_endpoint():
    r = client.get("/alerts/runs/integrity/dashboard/telegram?limit=10&max_chars=120")
    assert r.status_code == 200
    data = r.json()
    assert "chunks" in data
    assert "chunks_with_index" in data
    assert "chunk_count" in data
    assert data["chunk_count"] >= 1
    assert all(len(chunk) <= 120 for chunk in data["chunks"])
    assert data["chunks_with_index"][0].startswith("[1/")


def test_alerts_runs_integrity_trends_endpoint():
    r = client.get("/alerts/runs/integrity/trends?limit=50")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "trend" in data
    assert isinstance(data["trend"], list)


def test_alerts_latest_run_integrity_issues_endpoint():
    r = client.get("/alerts/runs/latest/integrity/issues")
    assert r.status_code == 200
    data = r.json()
    assert "exists" in data
    assert "run_id" in data


def test_alerts_run_integrity_issues_endpoint():
    run_id = "does-not-exist"
    r = client.get(f"/alerts/runs/{run_id}/integrity/issues")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "issue_count" in data
    assert isinstance(data["issues"], list)


def test_alerts_run_events_endpoint():
    email = f"runevents-{uuid4().hex[:8]}@example.com"
    run_id = "api-run-events"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get(f"/alerts/runs/{run_id}/events")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert isinstance(data["events"], list)


def test_alerts_run_events_endpoint_filters():
    email = f"runeventsf-{uuid4().hex[:8]}@example.com"
    run_id = "api-run-events-filter"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 10,
            "generate_mark_read": False,
            "dispatch_limit": 10,
            "retry_limit": 10,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get(f"/alerts/runs/{run_id}/events?kind=dispatch-fallback&status=executed")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["events"], list)
    assert all(item.get("kind") == "dispatch-fallback" for item in data["events"])


def test_alerts_latest_run_summary_endpoint():
    run_id = f"latest-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": run_id,
        },
    )

    r = client.get('/alerts/runs/latest/summary')
    assert r.status_code == 200
    data = r.json()
    assert data['exists'] is True
    assert data['run_id'] is not None
    assert isinstance(data['summary'], dict)


def test_alerts_run_events_endpoint_pagination():
    run_id = "api-run-events-page"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get(f"/alerts/runs/{run_id}/events?limit=1&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["events"], list)
    assert len(data["events"]) <= 1


def test_alerts_latest_run_events_endpoint():
    run_id = f"latest-events-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get('/alerts/runs/latest/events?kind=dispatch-fallback')
    assert r.status_code == 200
    data = r.json()
    assert data['exists'] is True
    assert data['run_id'] is not None
    assert isinstance(data['events'], list)


def test_alerts_run_events_csv_endpoint():
    run_id = f"events-csv-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get(f"/alerts/runs/{run_id}/events/csv?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "csv" in data
    assert "dispatch-fallback" in data["csv"]


def test_alerts_latest_run_events_csv_endpoint():
    run_id = f"latest-events-csv-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )

    r = client.get("/alerts/runs/latest/events/csv?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "csv" in data


def test_alerts_run_integrity_issues_markdown_endpoint():
    run_id = "missing-run-md"
    r = client.get(f"/alerts/runs/{run_id}/integrity/issues/markdown")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "markdown" in data
    assert f"# Run Integrity Issues — {run_id}" in data["markdown"]


def test_alerts_run_integrity_issues_telegram_endpoint():
    run_id = "missing-run-tg"
    r = client.get(f"/alerts/runs/{run_id}/integrity/issues/telegram?max_chars=120")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert data["chunk_count"] >= 1
    assert all(len(chunk) <= 120 for chunk in data["chunks"])
    assert data["chunks_with_index"][0].startswith("[1/")


def test_alerts_latest_run_integrity_issues_markdown_and_telegram_endpoints():
    run_id = f"latest-issues-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": run_id,
        },
    )

    md = client.get("/alerts/runs/latest/integrity/issues/markdown")
    assert md.status_code == 200
    md_data = md.json()
    assert md_data["exists"] is True
    assert md_data["run_id"] is not None
    assert "markdown" in md_data

    tg = client.get("/alerts/runs/latest/integrity/issues/telegram?max_chars=120")
    assert tg.status_code == 200
    tg_data = tg.json()
    assert tg_data["exists"] is True
    assert tg_data["run_id"] is not None
    assert tg_data["chunk_count"] >= 1


def test_alerts_run_integrity_issues_csv_endpoint():
    run_id = "missing-run-csv"
    r = client.get(f"/alerts/runs/{run_id}/integrity/issues/csv")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "csv" in data
    assert "run_id,ok,issue_count" in data["csv"]


def test_alerts_latest_run_integrity_issues_csv_endpoint():
    run_id = f"latest-issues-csv-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": run_id,
        },
    )

    r = client.get("/alerts/runs/latest/integrity/issues/csv")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "csv" in data


def test_alerts_run_incident_endpoint():
    run_id = f"incident-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get(f"/alerts/runs/{run_id}/incident?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "summary" in data and "integrity" in data and "issues" in data and "events" in data


def test_alerts_latest_run_incident_endpoint():
    run_id = f"latest-incident-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get("/alerts/runs/latest/incident?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "incident" in data and isinstance(data["incident"], dict)


def test_alerts_run_incident_markdown_endpoint():
    run_id = f"incident-md-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get(f"/alerts/runs/{run_id}/incident/markdown?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "markdown" in data
    assert f"# Run Incident — {run_id}" in data["markdown"]


def test_alerts_latest_run_incident_markdown_endpoint():
    run_id = f"latest-incident-md-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get("/alerts/runs/latest/incident/markdown?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "markdown" in data


def test_alerts_run_incident_telegram_endpoint():
    run_id = f"incident-tg-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get(f"/alerts/runs/{run_id}/incident/telegram?kind=dispatch-fallback&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert data["chunk_count"] >= 1
    assert data["chunks_with_index"][0].startswith("[1/")


def test_alerts_latest_run_incident_telegram_endpoint():
    run_id = f"latest-incident-tg-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get("/alerts/runs/latest/incident/telegram?kind=dispatch-fallback&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert data["chunk_count"] >= 1


def test_alerts_run_incident_csv_endpoint():
    run_id = f"incident-csv-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get(f"/alerts/runs/{run_id}/incident/csv?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "csv" in data
    assert "run_id,summary_exists" in data["csv"]


def test_alerts_latest_run_incident_csv_endpoint():
    run_id = f"latest-incident-csv-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get("/alerts/runs/latest/incident/csv?kind=dispatch-fallback")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "csv" in data


def test_alerts_run_incident_packet_endpoint():
    run_id = f"incident-packet-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get(f"/alerts/runs/{run_id}/incident/packet?kind=dispatch-fallback&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "incident" in data
    assert "markdown" in data
    assert "csv" in data
    assert "telegram" in data


def test_alerts_latest_run_incident_packet_endpoint():
    run_id = f"latest-incident-packet-{uuid4().hex[:8]}"
    client.post(
        "/alerts/cron/tick",
        json={
            "max_alerts": 5,
            "generate_mark_read": False,
            "dispatch_limit": 5,
            "retry_limit": 5,
            "dispatch_dry_run": False,
            "dispatch_provider": "unknown-provider",
            "run_id": run_id,
        },
    )
    r = client.get("/alerts/runs/latest/incident/packet?kind=dispatch-fallback&max_chars=200")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["run_id"] is not None
    assert "packet" in data and isinstance(data["packet"], dict)
