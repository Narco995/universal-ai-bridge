from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class BridgeError(Exception):
    """Base exception for expected Bridge workflow errors."""


class NotFound(BridgeError):
    pass


class Conflict(BridgeError):
    pass


class Forbidden(BridgeError):
    pass


class ApprovalRequired(BridgeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class BridgeService:
    """SQLite-backed workflow. All transports should call this service."""

    TERMINAL_VISIBLE_STATES = {"revealed", "decided", "awaiting_approval", "approved", "rejected", "changes_requested", "implemented"}

    def __init__(self, database: str | Path = "bridge.sqlite3") -> None:
        self.database = str(database)
        if self.database == ":memory:":
            raise ValueError("a persistent SQLite file path is required; :memory: is not supported across Bridge connections")
        Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    acceptance_criteria_json TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK (mode IN ('independent', 'open')),
                    required_authors_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    revealed_at TEXT,
                    current_decision_id TEXT
                );
                CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    submission_method TEXT NOT NULL DEFAULT 'manual',
                    UNIQUE(task_id, author)
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    choice TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    supporting_position_ids_json TEXT NOT NULL,
                    considered_not_chosen_ids_json TEXT NOT NULL,
                    requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0, 1)),
                    status TEXT NOT NULL,
                    supersedes_decision_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (action IN ('approve', 'reject', 'request_changes')),
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    kind TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    sha256 TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_positions_task ON positions(task_id);
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_task ON decisions(task_id, created_at);
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END;
                """
            )

                """
            )

    def _append_event(
        self,
        db: sqlite3.Connection,
        event_type: str,
        task_id: str,
        actor: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        previous = db.execute("SELECT event_hash FROM events ORDER BY event_id DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        occurred_at = _now()
        payload_json = _json(payload)
        canonical = _json({
            "event_type": event_type,
            "task_id": task_id,
            "actor": actor,
            "payload_json": payload_json,
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
        })
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        cursor = db.execute(
            """INSERT INTO events(event_type, task_id, actor, payload_json, occurred_at, previous_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, task_id, actor, payload_json, occurred_at, previous_hash, event_hash),
        )
        return {
            "event_id": cursor.lastrowid,
            "event_type": event_type,
            "task_id": task_id,
            "actor": actor,
            "payload": payload,
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        }

    @staticmethod
    def _string_list(value: Any, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"{field_name} must be a list of strings")
        return value

    @staticmethod
    def _task_row(db: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFound(f"Task not found: {task_id}")
        return row

    @staticmethod
    def _task_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "objective": row["objective"],
            "acceptance_criteria": json.loads(row["acceptance_criteria_json"]),
            "mode": row["mode"],
            "required_authors": json.loads(row["required_authors_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "revealed_at": row["revealed_at"],
            "current_decision_id": row["current_decision_id"],
        }

    def create_task(
        self,
        objective: str,
        acceptance_criteria: list[str],
        mode: str = "independent",
        required_authors: list[str] | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        objective = objective.strip()
        criteria_input = self._string_list(acceptance_criteria, "acceptance_criteria")
