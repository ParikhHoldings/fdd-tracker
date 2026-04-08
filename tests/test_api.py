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
