"""
Local SQLite-based lead tracking for the LeadPoet miner.

Always-on: every submission attempt is recorded regardless of environment
variables. Rejection feedback is fetched periodically and merged into
existing records.

Database: data/leads.db
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional


class LeadTracker:
    DB_PATH = os.path.join("data", "leads.db")

    def __init__(self, db_path: str = None):
        self._db_path = db_path or self.DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id             TEXT,
                status              TEXT NOT NULL,
                submitted_at        TEXT NOT NULL,
                business            TEXT NOT NULL DEFAULT '',
                full_name           TEXT NOT NULL DEFAULT '',
                email               TEXT NOT NULL DEFAULT '',
                role                TEXT NOT NULL DEFAULT '',
                industry            TEXT NOT NULL DEFAULT '',
                sub_industry        TEXT NOT NULL DEFAULT '',
                country             TEXT NOT NULL DEFAULT '',
                city                TEXT NOT NULL DEFAULT '',
                state               TEXT NOT NULL DEFAULT '',
                linkedin            TEXT NOT NULL DEFAULT '',
                website             TEXT NOT NULL DEFAULT '',
                source_url          TEXT NOT NULL DEFAULT '',
                source_type         TEXT NOT NULL DEFAULT '',
                employee_count      TEXT NOT NULL DEFAULT '',
                full_payload        TEXT,
                rejection_reason    TEXT,
                rejected_by         INTEGER,
                total_validators    INTEGER,
                common_failures     TEXT,
                consensus_timestamp TEXT,
                epoch_number        INTEGER,
                feedback_fetched_at TEXT,
                storage_backends    TEXT,
                rate_limit_subs     INTEGER,
                rate_limit_rejs     INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
            CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
            CREATE INDEX IF NOT EXISTS idx_leads_lead_id ON leads(lead_id);
            CREATE INDEX IF NOT EXISTS idx_leads_submitted_at ON leads(submitted_at);
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def log_submission(
        self,
        lead: Dict,
        status: str,
        lead_id: str = None,
        verification_result: Dict = None,
    ) -> int:
        """Record a submission attempt. Returns the row id."""
        storage_backends = None
        rate_limit_subs = None
        rate_limit_rejs = None

        if verification_result:
            backends = verification_result.get("storage_backends", [])
            storage_backends = (
                ",".join(backends) if isinstance(backends, list) else str(backends)
            )
            stats = verification_result.get("rate_limit_stats", {})
            rate_limit_subs = stats.get("submissions")
            rate_limit_rejs = stats.get("rejections")

        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO leads
               (lead_id, status, submitted_at,
                business, full_name, email, role, industry, sub_industry,
                country, city, state, linkedin, website,
                source_url, source_type, employee_count,
                full_payload,
                storage_backends, rate_limit_subs, rate_limit_rejs)
               VALUES (?,?,?, ?,?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?, ?,?,?)""",
            (
                lead_id,
                status,
                datetime.now(timezone.utc).isoformat(),
                lead.get("business", ""),
                lead.get("full_name", ""),
                lead.get("email", ""),
                lead.get("role", ""),
                lead.get("industry", ""),
                lead.get("sub_industry", ""),
                lead.get("country", ""),
                lead.get("city", ""),
                lead.get("state", ""),
                lead.get("linkedin", ""),
                lead.get("website", ""),
                lead.get("source_url", ""),
                lead.get("source_type", ""),
                lead.get("employee_count", ""),
                json.dumps(lead, default=str),
                storage_backends,
                rate_limit_subs,
                rate_limit_rejs,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def update_rejection_feedback(self, lead_id: str, feedback: Dict) -> bool:
        """Update a verified lead with rejection feedback from validators."""
        summary = feedback.get("rejection_summary", {})
        failures = summary.get("common_failures", [])
        common_failures_json = json.dumps(failures)

        # Build human-readable reason
        reason_parts = []
        for f in failures:
            name = f.get("check_name", "unknown")
            msg = f.get("message", "")
            reason_parts.append(f"{name}: {msg}" if msg else name)
        rejection_reason = "; ".join(reason_parts) if reason_parts else "Unknown"

        conn = self._get_conn()
        cursor = conn.execute(
            """UPDATE leads SET
                status              = 'rejected_consensus',
                rejection_reason    = ?,
                rejected_by         = ?,
                total_validators    = ?,
                common_failures     = ?,
                consensus_timestamp = ?,
                epoch_number        = ?,
                feedback_fetched_at = ?
               WHERE lead_id = ? AND feedback_fetched_at IS NULL""",
            (
                rejection_reason,
                summary.get("rejected_by"),
                summary.get("total_validators"),
                common_failures_json,
                feedback.get("consensus_timestamp"),
                feedback.get("epoch_number"),
                datetime.now(timezone.utc).isoformat(),
                lead_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_verified_lead_ids_without_feedback(self, limit: int = 200) -> List[str]:
        """Return lead_ids that were verified but haven't received feedback yet."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT lead_id FROM leads
               WHERE status = 'verified'
                 AND feedback_fetched_at IS NULL
                 AND lead_id IS NOT NULL
               ORDER BY submitted_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [row["lead_id"] for row in rows]

    def query_leads(
        self,
        status: str = None,
        industry: str = None,
        date_from: str = None,
        date_to: str = None,
        email: str = None,
        rejection_reason_contains: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Query leads with optional filters."""
        where_clauses = []
        params: list = []

        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if industry:
            where_clauses.append("industry LIKE ?")
            params.append(f"%{industry}%")
        if date_from:
            where_clauses.append("submitted_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("submitted_at <= ?")
            params.append(date_to)
        if email:
            where_clauses.append("email LIKE ?")
            params.append(f"%{email}%")
        if rejection_reason_contains:
            where_clauses.append("rejection_reason LIKE ?")
            params.append(f"%{rejection_reason_contains}%")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = f"""SELECT * FROM leads WHERE {where_sql}
                  ORDER BY submitted_at DESC LIMIT ? OFFSET ?"""
        params.extend([limit, offset])

        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> Dict:
        """Return aggregate statistics."""
        conn = self._get_conn()

        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM leads GROUP BY status ORDER BY cnt DESC"
        ).fetchall()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_total = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE submitted_at >= ?", (today,)
        ).fetchone()[0]
        today_verified = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE submitted_at >= ? AND status = 'verified'",
            (today,),
        ).fetchone()[0]
        today_rejected = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE submitted_at >= ? AND status IN ('gateway_rejected', 'rejected_consensus')",
            (today,),
        ).fetchone()[0]

        top_reasons = conn.execute(
            """SELECT rejection_reason, COUNT(*) as cnt FROM leads
               WHERE rejection_reason IS NOT NULL
               GROUP BY rejection_reason ORDER BY cnt DESC LIMIT 15"""
        ).fetchall()

        return {
            "total": total,
            "by_status": {row["status"]: row["cnt"] for row in by_status},
            "today_total": today_total,
            "today_verified": today_verified,
            "today_rejected": today_rejected,
            "top_rejection_reasons": [
                {"reason": row["rejection_reason"], "count": row["cnt"]}
                for row in top_reasons
            ],
        }
