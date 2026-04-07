import json
import tempfile
from pathlib import Path

from fdd_tracker.db import ensure_db
from fdd_tracker.services.ingest import refresh_state_source_cache, run_ingestion, slugify


class TestSlugify:
    def test_simple_name(self):
        assert slugify("Chick-fil-A") == "chick-fil-a"

    def test_spaces_become_hyphens(self):
        assert slugify("Taco Bell") == "taco-bell"

    def test_special_chars_become_hyphens(self):
        assert slugify("McDonald's") == "mcdonald-s"

    def test_multiple_special_chars_collapse(self):
        assert slugify("Pizza & Pasta") == "pizza-pasta"

    def test_leading_trailing_stripped(self):
        assert slugify("  Test Franchise!  ") == "test-franchise"

    def test_numbers_preserved(self):
        assert slugify("7-Eleven") == "7-eleven"


class TestRunIngestion:
    def test_empty_sources_return_zero_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            ensure_db(db_path)

            ftc_path = str(Path(tmpdir) / "ftc.json")
            state_path = str(Path(tmpdir) / "state.json")

            result = run_ingestion(ftc_path=ftc_path, state_path=state_path, db_path=db_path)

            assert result["total_seen"] == 0
            assert result["inserted_or_updated"] == 0
            assert result["sources_breakdown"] == {"ftc": 0, "state": 0}

    def test_ingestion_with_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            ensure_db(db_path)

            ftc_data = [
                {"franchise_name": "Acme Burgers", "filing_url": "https://ftc.gov/acme.pdf", "filed_on": "2026-01-15"},
            ]
            ftc_path = str(Path(tmpdir) / "ftc.json")
            with open(ftc_path, "w") as f:
                json.dump(ftc_data, f)

            state_data = [
                {"state": "CA", "franchise_name": "West Wings", "filing_url": "https://ca.gov/wings.pdf", "filed_on": "2026-02-01"},
                {"state": "NY", "franchise_name": "East Coffee", "filing_url": "https://ny.gov/coffee.pdf", "filed_on": "2026-02-10"},
            ]
            state_path = str(Path(tmpdir) / "state.json")
            with open(state_path, "w") as f:
                json.dump(state_data, f)

            result = run_ingestion(ftc_path=ftc_path, state_path=state_path, db_path=db_path)

            assert result["total_seen"] == 3
            assert result["inserted_or_updated"] == 3
            assert result["sources_breakdown"]["ftc"] == 1
            assert result["sources_breakdown"]["state"] == 2

    def test_ingestion_with_state_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            ensure_db(db_path)

            ftc_path = str(Path(tmpdir) / "ftc.json")
            with open(ftc_path, "w") as f:
                json.dump([], f)

            state_data = [
                {"state": "CA", "franchise_name": "West Wings", "filing_url": "https://ca.gov/wings.pdf", "filed_on": "2026-02-01"},
                {"state": "NY", "franchise_name": "East Coffee", "filing_url": "https://ny.gov/coffee.pdf", "filed_on": "2026-02-10"},
                {"state": "IL", "franchise_name": "Midwest Tacos", "filing_url": "https://il.gov/tacos.pdf", "filed_on": "2026-02-15"},
            ]
            state_path = str(Path(tmpdir) / "state.json")
            with open(state_path, "w") as f:
                json.dump(state_data, f)

            result = run_ingestion(states=["CA"], ftc_path=ftc_path, state_path=state_path, db_path=db_path)

            assert result["total_seen"] == 1
            assert result["inserted_or_updated"] == 1
            assert result["sources_breakdown"]["state"] == 1

    def test_upsert_idempotency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            ensure_db(db_path)

            ftc_data = [
                {"franchise_name": "Acme Burgers", "filing_url": "https://ftc.gov/acme.pdf", "filed_on": "2026-01-15"},
            ]
            ftc_path = str(Path(tmpdir) / "ftc.json")
            with open(ftc_path, "w") as f:
                json.dump(ftc_data, f)

            state_path = str(Path(tmpdir) / "state.json")
            with open(state_path, "w") as f:
                json.dump([], f)

            result1 = run_ingestion(ftc_path=ftc_path, state_path=state_path, db_path=db_path)
            assert result1["inserted_or_updated"] == 1

            result2 = run_ingestion(ftc_path=ftc_path, state_path=state_path, db_path=db_path)
            assert result2["total_seen"] == 1
            assert result2["inserted_or_updated"] == 1


class TestRefreshStateSourceCache:
    def test_refresh_state_source_cache_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "state_filings.json")

            ca_text = """
            <rss><channel>
              <item><title>Alpha CA</title><link>https://ca.example/alpha.pdf</link><filed_on>2026-04-01</filed_on></item>
            </channel></rss>
            """
            il_text = """
            <feed>
              <entry><company>Beta IL</company><link href=\"https://il.example/beta.pdf\"/><effective_date>04/02/2026</effective_date></entry>
            </feed>
            """

            result = refresh_state_source_cache(
                states=["CA", "IL"],
                output_path=out_path,
                ca_text=ca_text,
                il_text=il_text,
            )

            assert result["written"] is True
            assert result["output_path"] == out_path
            assert result["records"] == 2

            with open(out_path, "r", encoding="utf-8") as f:
                rows = json.load(f)
            assert len(rows) == 2
            assert {r["state"] for r in rows} == {"CA", "IL"}
