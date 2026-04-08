from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "fdd_tracker.db"


def ensure_db(path: str | None = None) -> str:
    db_path = Path(path) if path else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                franchise_slug TEXT NOT NULL,
                source TEXT NOT NULL,
                filed_on TEXT,
                document_url TEXT NOT NULL,
                document_hash TEXT,
                UNIQUE(franchise_slug, source, document_url)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS change_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                franchise_slug TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                categories TEXT NOT NULL,
                highlights TEXT NOT NULL,
                risk_level TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                franchise_slug TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                UNIQUE(email, franchise_slug)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                franchise_slug TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                read_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                UNIQUE(email, franchise_slug, generated_at)
            )
            """
        )
        conn.commit()
    return str(db_path)


@contextmanager
def get_conn(path: str | None = None):
    db = ensure_db(path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
