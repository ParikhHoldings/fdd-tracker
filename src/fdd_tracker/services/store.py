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


def get_latest_filings(franchise_slug: str, limit: int = 2, db_path: str | None = None) -> list[dict]:
    """Get latest filings for a franchise, ordered by filed_on desc nulls last, then id desc."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, franchise_slug, source, filed_on, document_url, document_hash
            FROM filings
            WHERE franchise_slug = ?
            ORDER BY filed_on IS NULL, filed_on DESC, id DESC
            LIMIT ?
            """,
            (franchise_slug, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "franchise_slug": row["franchise_slug"],
            "source": row["source"],
            "filed_on": row["filed_on"],
            "document_url": row["document_url"],
            "document_hash": row["document_hash"],
        }
        for row in rows
    ]


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


def upsert_watchlist(email: str, franchise_slug: str, db_path: str | None = None) -> dict:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO watchlists(email, franchise_slug)
            VALUES (?, ?)
            ON CONFLICT(email, franchise_slug) DO NOTHING
            """,
            (email, franchise_slug),
        )
        conn.commit()
        created = cur.rowcount > 0

        row = conn.execute(
            """
            SELECT id, email, franchise_slug, created_at
            FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (email, franchise_slug),
        ).fetchone()

    return {
        "created": created,
        "id": row["id"],
        "email": row["email"],
        "franchise_slug": row["franchise_slug"],
        "created_at": row["created_at"],
    }


def get_watchlists(email: str | None = None, db_path: str | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        if email:
            rows = conn.execute(
                """
                SELECT id, email, franchise_slug, created_at
                FROM watchlists
                WHERE email = ?
                ORDER BY created_at DESC
                """,
                (email,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, email, franchise_slug, created_at
                FROM watchlists
                ORDER BY created_at DESC
                """
            ).fetchall()

    return [
        {
            "id": row["id"],
            "email": row["email"],
            "franchise_slug": row["franchise_slug"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def delete_watchlist(email: str, franchise_slug: str, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            DELETE FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (email, franchise_slug),
        )
        conn.commit()
        return cur.rowcount
