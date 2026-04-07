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
