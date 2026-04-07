import json
import tempfile
from pathlib import Path

from fdd_tracker.ingestion.ftc import fetch_ftc_filings
from fdd_tracker.ingestion.state_portals import fetch_state_filings


class TestFTCLoader:
    def test_missing_file_returns_empty(self):
        result = list(fetch_ftc_filings(path="/nonexistent/path.json"))
        assert result == []

    def test_valid_file_returns_records(self):
        data = [
            {"franchise_name": "Acme Burgers", "filing_url": "https://ftc.gov/acme.pdf", "filed_on": "2026-01-15"},
            {"franchise_name": "Best Pizza", "filing_url": "https://ftc.gov/pizza.pdf", "filed_on": None},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            temp_path = f.name

        try:
            records = list(fetch_ftc_filings(path=temp_path))
            assert len(records) == 2
            assert records[0].franchise_name == "Acme Burgers"
            assert records[0].filing_url == "https://ftc.gov/acme.pdf"
            assert records[0].filed_on == "2026-01-15"
            assert records[1].franchise_name == "Best Pizza"
            assert records[1].filed_on is None
        finally:
            Path(temp_path).unlink()


class TestStatePortalLoader:
    def test_missing_file_returns_empty(self):
        result = list(fetch_state_filings(path="/nonexistent/path.json"))
        assert result == []

    def test_valid_file_returns_records(self):
        data = [
            {"state": "CA", "franchise_name": "West Coast Wings", "filing_url": "https://ca.gov/wings.pdf", "filed_on": "2026-02-01"},
            {"state": "NY", "franchise_name": "East Coast Coffee", "filing_url": "https://ny.gov/coffee.pdf", "filed_on": "2026-02-10"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            temp_path = f.name

        try:
            records = list(fetch_state_filings(path=temp_path))
            assert len(records) == 2
            assert records[0].state == "CA"
            assert records[0].franchise_name == "West Coast Wings"
            assert records[1].state == "NY"
        finally:
            Path(temp_path).unlink()

    def test_filter_by_states(self):
        data = [
            {"state": "CA", "franchise_name": "West Coast Wings", "filing_url": "https://ca.gov/wings.pdf", "filed_on": "2026-02-01"},
            {"state": "NY", "franchise_name": "East Coast Coffee", "filing_url": "https://ny.gov/coffee.pdf", "filed_on": "2026-02-10"},
            {"state": "IL", "franchise_name": "Midwest Tacos", "filing_url": "https://il.gov/tacos.pdf", "filed_on": "2026-02-15"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            temp_path = f.name

        try:
            records = list(fetch_state_filings(states=["CA", "IL"], path=temp_path))
            assert len(records) == 2
            states = {r.state for r in records}
            assert states == {"CA", "IL"}
        finally:
            Path(temp_path).unlink()
