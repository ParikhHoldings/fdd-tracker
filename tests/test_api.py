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
