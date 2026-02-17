from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS machines (
    machine_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    location TEXT,
    tool_sop TEXT,
    policy_documents TEXT,
    standard_recipies TEXT,
    manual_ref TEXT
);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id INTEGER PRIMARY KEY,
    machine_id INTEGER,
    complaint_description TEXT,
    time_of_complaint TEXT,
    status INTEGER,
    status_resolved TEXT
);

CREATE TABLE IF NOT EXISTS trouble_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER,
    timestamp TEXT,
    diagnosis TEXT,
    action_taken TEXT,
    comments TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    machine_id INTEGER,
    doc_type TEXT,
    path TEXT,
    text TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT,
    machine_id INTEGER,
    doc_type TEXT,
    text TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    machine_id INTEGER,
    issue TEXT,
    helpful INTEGER,
    workaround TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS troubleshoot_sessions (
    session_id TEXT PRIMARY KEY,
    machine_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    triage TEXT NOT NULL,
    flow_json TEXT NOT NULL,
    current_node_id TEXT NOT NULL,
    is_closed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS troubleshoot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    response TEXT NOT NULL,
    next_node_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recent_machine_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER NOT NULL,
    issue TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def replace_machines(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM machines")
            conn.executemany(
                """
                INSERT INTO machines (
                    machine_id, name, category, location,
                    tool_sop, policy_documents, standard_recipies, manual_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.get("machine_id"),
                        row.get("name", "Unknown"),
                        row.get("category"),
                        row.get("location"),
                        row.get("tool_sop"),
                        row.get("policy_documents"),
                        row.get("standard_recipies"),
                        row.get("manual_ref"),
                    )
                    for row in rows
                ],
            )

    def replace_complaints(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM complaints")
            conn.executemany(
                """
                INSERT INTO complaints (
                    complaint_id, machine_id, complaint_description,
                    time_of_complaint, status, status_resolved
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.get("complaint_id"),
                        row.get("machine_id"),
                        row.get("complaint_description"),
                        row.get("time_of_complaint"),
                        row.get("status"),
                        row.get("status_resolved"),
                    )
                    for row in rows
                ],
            )

    def replace_trouble_events(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM trouble_events")
            conn.executemany(
                """
                INSERT INTO trouble_events (
                    complaint_id, timestamp, diagnosis, action_taken, comments
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.get("complaint_id"),
                        row.get("timestamp"),
                        row.get("diagnosis"),
                        row.get("action_taken"),
                        row.get("comments"),
                    )
                    for row in rows
                ],
            )

    def replace_documents(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents")
            conn.executemany(
                """
                INSERT INTO documents (doc_id, machine_id, doc_type, path, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.get("doc_id"),
                        row.get("machine_id"),
                        row.get("doc_type"),
                        row.get("path"),
                        row.get("text"),
                    )
                    for row in rows
                ],
            )

    def upsert_document(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (doc_id, machine_id, doc_type, path, text)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    machine_id = excluded.machine_id,
                    doc_type = excluded.doc_type,
                    path = excluded.path,
                    text = excluded.text
                """,
                (
                    row.get("doc_id"),
                    row.get("machine_id"),
                    row.get("doc_type"),
                    row.get("path"),
                    row.get("text"),
                ),
            )

    def replace_chunks(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.executemany(
                """
                INSERT INTO chunks (chunk_id, doc_id, machine_id, doc_type, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.get("chunk_id"),
                        row.get("doc_id"),
                        row.get("machine_id"),
                        row.get("doc_type"),
                        row.get("text"),
                    )
                    for row in rows
                ],
            )

    def replace_chunks_for_doc(self, doc_id: str, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            if rows:
                conn.executemany(
                    """
                    INSERT INTO chunks (chunk_id, doc_id, machine_id, doc_type, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row.get("chunk_id"),
                            row.get("doc_id"),
                            row.get("machine_id"),
                            row.get("doc_type"),
                            row.get("text"),
                        )
                        for row in rows
                    ],
                )

    def list_machines(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT machine_id, name, category, location FROM machines ORDER BY machine_id"
            )
            return [dict(row) for row in cur.fetchall()]

    def list_recent_machines(self, limit: int = 8) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT r.machine_id, m.name, r.issue, r.session_id, r.created_at
                FROM recent_machine_access r
                LEFT JOIN machines m ON m.machine_id = r.machine_id
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        # dedupe while keeping latest first
        deduped: list[dict[str, Any]] = []
        seen: set[int] = set()
        for row in rows:
            machine_id = int(row.get("machine_id") or 0)
            if machine_id in seen:
                continue
            deduped.append(row)
            seen.add(machine_id)
        return deduped

    def list_chunks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT chunk_id, doc_id, machine_id, doc_type, text FROM chunks"
            )
            return [dict(row) for row in cur.fetchall()]

    def document_lookup(self) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute("SELECT doc_id, machine_id, doc_type, path FROM documents")
            return {row["doc_id"]: dict(row) for row in cur.fetchall()}

    def list_machine_complaints(self, machine_id: int, limit: int = 150) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT complaint_id, machine_id, complaint_description, status, status_resolved, time_of_complaint
                FROM complaints
                WHERE machine_id = ?
                ORDER BY time_of_complaint DESC
                LIMIT ?
                """,
                (machine_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def next_complaint_id(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(complaint_id), 0) AS max_id FROM complaints").fetchone()
            return int((row["max_id"] if row else 0) or 0) + 1

    def upsert_machine(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO machines (
                    machine_id, name, category, location,
                    tool_sop, policy_documents, standard_recipies, manual_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    location = excluded.location,
                    tool_sop = excluded.tool_sop,
                    policy_documents = excluded.policy_documents,
                    standard_recipies = excluded.standard_recipies,
                    manual_ref = excluded.manual_ref
                """,
                (
                    row.get("machine_id"),
                    row.get("name", "Unknown"),
                    row.get("category"),
                    row.get("location"),
                    row.get("tool_sop"),
                    row.get("policy_documents"),
                    row.get("standard_recipies"),
                    row.get("manual_ref"),
                ),
            )

    def upsert_complaint(self, row: dict[str, Any]) -> int:
        complaint_id = int(row.get("complaint_id") or self.next_complaint_id())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO complaints (
                    complaint_id, machine_id, complaint_description,
                    time_of_complaint, status, status_resolved
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(complaint_id) DO UPDATE SET
                    machine_id = excluded.machine_id,
                    complaint_description = excluded.complaint_description,
                    time_of_complaint = excluded.time_of_complaint,
                    status = excluded.status,
                    status_resolved = excluded.status_resolved
                """,
                (
                    complaint_id,
                    row.get("machine_id"),
                    row.get("complaint_description"),
                    row.get("time_of_complaint"),
                    row.get("status"),
                    row.get("status_resolved"),
                ),
            )
        return complaint_id

    def insert_trouble_event_row(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trouble_events (complaint_id, timestamp, diagnosis, action_taken, comments)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row.get("complaint_id"),
                    row.get("timestamp"),
                    row.get("diagnosis"),
                    row.get("action_taken"),
                    row.get("comments"),
                ),
            )

    def list_trouble_events(self, complaint_ids: list[int]) -> list[dict[str, Any]]:
        if not complaint_ids:
            return []
        placeholders = ",".join(["?"] * len(complaint_ids))
        query = (
            "SELECT complaint_id, timestamp, diagnosis, action_taken, comments "
            "FROM trouble_events WHERE complaint_id IN (" + placeholders + ")"
        )
        with self.connect() as conn:
            cur = conn.execute(query, complaint_ids)
            return [dict(row) for row in cur.fetchall()]

    def insert_feedback(
        self,
        session_id: str,
        machine_id: int,
        issue: str,
        helpful: bool,
        workaround: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback (session_id, machine_id, issue, helpful, workaround)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, machine_id, issue, int(helpful), workaround),
            )

    def list_feedback_for_machine(self, machine_id: int, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT session_id, machine_id, issue, helpful, workaround, created_at
                FROM feedback
                WHERE machine_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (machine_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def record_recent_machine(self, machine_id: int, issue: str, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO recent_machine_access (machine_id, issue, session_id)
                VALUES (?, ?, ?)
                """,
                (machine_id, issue, session_id),
            )

    def insert_audit_log(self, event_type: str, payload_json: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (event_type, payload_json)
                VALUES (?, ?)
                """,
                (event_type, payload_json),
            )

    def create_user(self, username: str, password_hash: str, role: str, is_active: bool = True) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (username, password_hash, role, int(is_active)),
            )
            return int(cur.lastrowid)

    def upsert_user(self, username: str, password_hash: str, role: str, is_active: bool = True) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    is_active = excluded.is_active
                """,
                (username, password_hash, role, int(is_active)),
            )
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            return int(row["id"]) if row else 0

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, is_active, created_at
                FROM users WHERE username = ?
                """,
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, is_active, created_at
                FROM users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def count_admin_users(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()
            return int(row["c"] if row else 0)

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, username, role, is_active, created_at
                FROM users
                ORDER BY id ASC
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def update_user(
        self,
        user_id: int,
        role: str | None = None,
        is_active: bool | None = None,
        password_hash: str | None = None,
    ) -> bool:
        assignments: list[str] = []
        params: list[Any] = []
        if role is not None:
            assignments.append("role = ?")
            params.append(role)
        if is_active is not None:
            assignments.append("is_active = ?")
            params.append(int(is_active))
        if password_hash is not None:
            assignments.append("password_hash = ?")
            params.append(password_hash)
        if not assignments:
            return False
        params.append(user_id)
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
            return cur.rowcount > 0

    def create_auth_session(
        self,
        session_id: str,
        user_id: int,
        token_hash: str,
        expires_at: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (session_id, user_id, token_hash, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, user_id, token_hash, expires_at),
            )

    def get_auth_session(self, token_hash: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT s.session_id, s.user_id, s.token_hash, s.expires_at, s.created_at, s.last_seen_at,
                       u.username, u.role, u.is_active
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            return dict(row) if row else None

    def touch_auth_session(self, session_id: str, expires_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE auth_sessions
                SET expires_at = ?, last_seen_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (expires_at, session_id),
            )

    def delete_auth_session_by_token(self, token_hash: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    def delete_auth_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))

    def delete_expired_auth_sessions(self, now_iso: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now_iso,))

    def create_troubleshoot_session(
        self,
        session_id: str,
        machine_id: int,
        question: str,
        triage: str,
        flow_json: str,
        current_node_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO troubleshoot_sessions (
                    session_id, machine_id, question, triage,
                    flow_json, current_node_id, is_closed
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (session_id, machine_id, question, triage, flow_json, current_node_id),
            )

    def get_troubleshoot_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, machine_id, question, triage,
                       flow_json, current_node_id, is_closed, created_at, updated_at
                FROM troubleshoot_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def update_troubleshoot_session(
        self,
        session_id: str,
        current_node_id: str,
        is_closed: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE troubleshoot_sessions
                SET current_node_id = ?, is_closed = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (current_node_id, int(is_closed), session_id),
            )

    def insert_troubleshoot_event(
        self,
        session_id: str,
        node_id: str,
        response: str,
        next_node_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO troubleshoot_events (session_id, node_id, response, next_node_id)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, node_id, response, next_node_id),
            )

    def admin_analytics(
        self,
        machine_id: int | None = None,
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        machine_filter = int(machine_id) if machine_id is not None else None
        category_filter = str(category or "").strip().lower()
        date_from_filter = str(date_from or "").strip()
        date_to_filter = str(date_to or "").strip()

        def complaint_filter_clauses(*, include_known_machine_only: bool, include_open_only: bool) -> tuple[list[str], list[Any]]:
            clauses: list[str] = []
            params: list[Any] = []
            if include_known_machine_only:
                clauses.extend(["c.machine_id IS NOT NULL", "c.machine_id != 0"])
            if include_open_only:
                clauses.append("c.status != 2")
            if machine_filter is not None:
                clauses.append("c.machine_id = ?")
                params.append(machine_filter)
            if category_filter:
                clauses.append("LOWER(COALESCE(m.category, '')) = ?")
                params.append(category_filter)
            if date_from_filter:
                clauses.append("SUBSTR(c.time_of_complaint, 1, 10) >= ?")
                params.append(date_from_filter)
            if date_to_filter:
                clauses.append("SUBSTR(c.time_of_complaint, 1, 10) <= ?")
                params.append(date_to_filter)
            return clauses, params

        def feedback_filter_clauses(*, include_failed_only: bool) -> tuple[list[str], list[Any]]:
            clauses: list[str] = []
            params: list[Any] = []
            if include_failed_only:
                clauses.append("f.helpful = 0")
            if machine_filter is not None:
                clauses.append("f.machine_id = ?")
                params.append(machine_filter)
            if category_filter:
                clauses.append("LOWER(COALESCE(m.category, '')) = ?")
                params.append(category_filter)
            if date_from_filter:
                clauses.append("SUBSTR(f.created_at, 1, 10) >= ?")
                params.append(date_from_filter)
            if date_to_filter:
                clauses.append("SUBSTR(f.created_at, 1, 10) <= ?")
                params.append(date_to_filter)
            return clauses, params

        with self.connect() as conn:
            top_clauses, top_params = complaint_filter_clauses(
                include_known_machine_only=True,
                include_open_only=False,
            )
            top_where = f"WHERE {' AND '.join(top_clauses)}" if top_clauses else ""
            top_breakdowns = conn.execute(
                f"""
                SELECT c.machine_id, m.name, COUNT(*) AS count
                FROM complaints c
                LEFT JOIN machines m ON m.machine_id = c.machine_id
                {top_where}
                GROUP BY c.machine_id
                ORDER BY count DESC
                LIMIT 10
                """,
                top_params,
            ).fetchall()

            category_clauses, category_params = complaint_filter_clauses(
                include_known_machine_only=True,
                include_open_only=False,
            )
            category_where = f"WHERE {' AND '.join(category_clauses)}" if category_clauses else ""
            category_breakdowns = conn.execute(
                f"""
                SELECT COALESCE(m.category, 'uncategorized') AS category, COUNT(*) AS count
                FROM complaints c
                LEFT JOIN machines m ON m.machine_id = c.machine_id
                {category_where}
                GROUP BY COALESCE(m.category, 'uncategorized')
                ORDER BY count DESC
                LIMIT 12
                """,
                category_params,
            ).fetchall()

            monthly_clauses, monthly_params = complaint_filter_clauses(
                include_known_machine_only=False,
                include_open_only=False,
            )
            monthly_clauses.insert(0, "c.time_of_complaint GLOB '????-??-*'")
            monthly_where = f"WHERE {' AND '.join(monthly_clauses)}" if monthly_clauses else ""
            monthly_breakdowns = conn.execute(
                f"""
                SELECT SUBSTR(c.time_of_complaint, 1, 7) AS month_key, COUNT(*) AS count
                FROM complaints c
                LEFT JOIN machines m ON m.machine_id = c.machine_id
                {monthly_where}
                GROUP BY SUBSTR(c.time_of_complaint, 1, 7)
                ORDER BY month_key DESC
                LIMIT 6
                """,
                monthly_params,
            ).fetchall()

            unresolved_clauses, unresolved_params = complaint_filter_clauses(
                include_known_machine_only=False,
                include_open_only=True,
            )
            unresolved_where = f"WHERE {' AND '.join(unresolved_clauses)}" if unresolved_clauses else ""
            unresolved = conn.execute(
                f"""
                SELECT c.complaint_id, c.machine_id, m.name, c.complaint_description, c.time_of_complaint
                FROM complaints c
                LEFT JOIN machines m ON m.machine_id = c.machine_id
                {unresolved_where}
                ORDER BY c.time_of_complaint DESC
                LIMIT 25
                """,
                unresolved_params,
            ).fetchall()

            failed_clauses, failed_params = feedback_filter_clauses(include_failed_only=True)
            failed_where = f"WHERE {' AND '.join(failed_clauses)}" if failed_clauses else ""
            failed_feedback = conn.execute(
                f"""
                SELECT f.session_id, f.machine_id, m.name, f.issue, f.workaround, f.created_at
                FROM feedback f
                LEFT JOIN machines m ON m.machine_id = f.machine_id
                {failed_where}
                ORDER BY f.created_at DESC
                LIMIT 25
                """,
                failed_params,
            ).fetchall()

            summary_clauses, summary_params = feedback_filter_clauses(include_failed_only=False)
            summary_where = f"WHERE {' AND '.join(summary_clauses)}" if summary_clauses else ""
            feedback_summary = conn.execute(
                f"""
                SELECT f.machine_id,
                       SUM(CASE WHEN f.helpful = 1 THEN 1 ELSE 0 END) AS helpful_count,
                       SUM(CASE WHEN f.helpful = 0 THEN 1 ELSE 0 END) AS not_helpful_count
                FROM feedback f
                LEFT JOIN machines m ON m.machine_id = f.machine_id
                {summary_where}
                GROUP BY f.machine_id
                ORDER BY (helpful_count + not_helpful_count) DESC
                LIMIT 10
                """,
                summary_params,
            ).fetchall()

        return {
            "top_breakdowns": [dict(row) for row in top_breakdowns],
            "category_breakdowns": [dict(row) for row in category_breakdowns],
            "monthly_breakdowns": [dict(row) for row in monthly_breakdowns],
            "unresolved_issues": [dict(row) for row in unresolved],
            "failed_feedback": [dict(row) for row in failed_feedback],
            "feedback_summary": [dict(row) for row in feedback_summary],
        }
