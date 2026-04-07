from __future__ import annotations

import json
from datetime import datetime

from fdd_tracker.db import get_conn
from fdd_tracker.models import ChangeSummary, Filing


def upsert_filing(filing: Filing, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO filings(franchise_slug, source, filed_on, document_url, document_hash)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(franchise_slug, source, document_url)
            DO UPDATE SET filed_on=excluded.filed_on, document_hash=excluded.document_hash
            """,
            (
                filing.franchise_slug,
                filing.source,
                filing.filed_on.isoformat() if filing.filed_on else None,
                filing.document_url,
                filing.document_hash,
            ),
        )
        conn.commit()
        return cur.rowcount


def insert_change_summary(summary: ChangeSummary, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO change_summaries(franchise_slug, generated_at, categories, highlights, risk_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary.franchise_slug,
                summary.generated_at.isoformat(),
                json.dumps(summary.categories),
                json.dumps(summary.highlights),
                summary.risk_level,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_recent_changes(franchise_slug: str, limit: int = 20, db_path: str | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT franchise_slug, generated_at, categories, highlights, risk_level
            FROM change_summaries
            WHERE franchise_slug = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (franchise_slug, limit),
        ).fetchall()

    out = []
    for row in rows:
        out.append(
            {
                "franchise_slug": row["franchise_slug"],
                "generated_at": row["generated_at"],
                "categories": json.loads(row["categories"]),
                "highlights": json.loads(row["highlights"]),
                "risk_level": row["risk_level"],
            }
        )
    return out


def seed_change_summary(franchise_slug: str, categories: list[str], risk_level: str = "medium", db_path: str | None = None):
    summary = ChangeSummary(
        franchise_slug=franchise_slug,
        generated_at=datetime.utcnow(),
        categories=categories,
        highlights=["seeded"],
        risk_level=risk_level,
    )
    return insert_change_summary(summary, db_path=db_path)
