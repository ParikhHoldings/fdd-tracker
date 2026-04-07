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
