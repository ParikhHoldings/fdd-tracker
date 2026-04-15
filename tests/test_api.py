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


def test_alerts_digest_preview_all_endpoint():
    email_a = f"digestpreview-all-a-{uuid4().hex[:8]}@example.com"
    email_b = f"digestpreview-all-b-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email_a, "franchise_slug": "chick-fil-a"})
    client.post("/watchlists", json={"email": email_b, "franchise_slug": "orangetheory"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    r = client.get("/alerts/digest/preview/all?max_alerts=10")
    assert r.status_code == 200
    data = r.json()
    assert data["emails_scanned"] >= 2
    assert data["returned"] >= 2
    assert isinstance(data["previews"], list)

    r2 = client.get("/alerts/digest/preview/all?max_alerts=10&unread_only=true")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["unread_only"] is True


def test_alerts_digest_preview_all_markdown_telegram_csv_packet_endpoints():
    email = f"digestpreview-all-view-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get("/alerts/digest/preview/all/markdown?max_alerts=10")
    assert md.status_code == 200
    assert "markdown" in md.json()
    assert "Digest Preview All Emails" in md.json()["markdown"]

    tg = client.get("/alerts/digest/preview/all/telegram?max_alerts=10&max_chars=200")
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd["chunk_count"] >= 1
    assert tgd["chunks_with_index"][0].startswith("[1/")

    csv_r = client.get("/alerts/digest/preview/all/csv?max_alerts=10")
    assert csv_r.status_code == 200
    assert "csv" in csv_r.json()
    assert "emails_scanned,returned,unread_only,email,has_unread" in csv_r.json()["csv"]

    packet_r = client.get("/alerts/digest/preview/all/packet?max_alerts=10&max_chars=200")
    assert packet_r.status_code == 200
    pkt = packet_r.json()
    assert "payload" in pkt
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

    r = client.get("/alerts/digest/preview/all/summary?max_alerts=10&top_n=1")
    assert r.status_code == 200
    data = r.json()
    assert data["emails_scanned"] >= 2
    assert data["top_n"] == 1
    assert len(data["top_unread_emails"]) <= 1
    assert "unread_alert_total" in data
    assert "top_unread_emails" in data and isinstance(data["top_unread_emails"], list)


def test_alerts_digest_preview_all_summary_markdown_and_telegram_endpoints():
    email = f"digestpreview-allsum-view-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    md = client.get("/alerts/digest/preview/all/summary/markdown?max_alerts=10&top_n=1")
    assert md.status_code == 200
    assert "markdown" in md.json()
    assert "Digest Preview All-Email Summary" in md.json()["markdown"]
    assert "Top Unread Emails (1)" in md.json()["markdown"]

    tg = client.get("/alerts/digest/preview/all/summary/telegram?max_alerts=10&top_n=1&max_chars=200")
    assert tg.status_code == 200
    tgd = tg.json()
    assert tgd["top_n"] == 1
    assert tgd["chunk_count"] >= 1
    assert tgd["chunks_with_index"][0].startswith("[1/")


def test_alerts_digest_preview_all_summary_csv_and_packet_endpoints():
    email = f"digestpreview-allsum-packet-{uuid4().hex[:8]}@example.com"
    client.post("/watchlists", json={"email": email, "franchise_slug": "chick-fil-a"})
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high")

    csv_r = client.get("/alerts/digest/preview/all/summary/csv?max_alerts=10&top_n=1")
    assert csv_r.status_code == 200
    assert "csv" in csv_r.json()
    assert "top_n" in csv_r.json()["csv"]

    packet_r = client.get("/alerts/digest/preview/all/summary/packet?max_alerts=10&top_n=1&max_chars=200")
    assert packet_r.status_code == 200
    pkt = packet_r.json()
    assert "summary" in pkt
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
