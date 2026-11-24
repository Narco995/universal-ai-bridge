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
        authors_input = self._string_list(required_authors, "required_authors")
        criteria = [item.strip() for item in criteria_input if item.strip()]
        authors = list(dict.fromkeys(a.strip() for a in authors_input if a.strip()))
        if not objective:
            raise ValueError("objective is required")
        if not criteria:
            raise ValueError("at least one acceptance criterion is required")
        if mode not in {"independent", "open"}:
            raise ValueError("mode must be 'independent' or 'open'")
        task_id, now = _id("task"), _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO tasks(task_id, objective, acceptance_criteria_json, mode, required_authors_json,
                   status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'collecting', ?, ?)""",
                (task_id, objective, _json(criteria), mode, _json(authors), now, now),
            )
            self._append_event(db, "task_created", task_id, actor, {
                "objective": objective,
                "acceptance_criteria": criteria,
                "mode": mode,
                "required_authors": authors,
                "submission_policy": "manual_until_provider_adapters_exist",
            })
            row = self._task_row(db, task_id)
            return self._task_dict(row)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connection() as db:
            return self._task_dict(self._task_row(db, task_id))

    def submit_position(self, task_id: str, author: str, content: str, actor: str = "human") -> dict[str, Any]:
        author, content = author.strip(), content.strip()
        if not author or not content:
            raise ValueError("author and content are required")
        position_id, now = _id("pos"), _now()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if task["status"] != "collecting":
                raise Conflict(f"positions cannot be submitted while task is {task['status']}")
            try:
                db.execute(
                    """INSERT INTO positions(position_id, task_id, author, content, content_hash, submitted_at,
                       submission_method) VALUES (?, ?, ?, ?, ?, ?, 'manual')""",
                    (position_id, task_id, author, content, content_hash, now),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict(f"{author} has already submitted a position for this task") from exc
            self._append_event(db, "position_submitted", task_id, actor, {
                "position_id": position_id,
                "author": author,
                "content": content,
                "content_hash": content_hash,
                "submission_method": "manual",
            })
            required = set(json.loads(task["required_authors_json"]))
            submitted = {r[0] for r in db.execute("SELECT author FROM positions WHERE task_id = ?", (task_id,)).fetchall()}
            if required and required.issubset(submitted):
                db.execute("UPDATE tasks SET status = 'ready_to_reveal', updated_at = ? WHERE task_id = ?", (now, task_id))
                self._append_event(db, "collection_ready", task_id, actor, {"reason": "all_required_authors_submitted"})
            row = db.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,)).fetchone()
            return self._position_dict(row, include_content=True)

    @staticmethod
    def _position_dict(row: sqlite3.Row, include_content: bool) -> dict[str, Any]:
        result = {
            "position_id": row["position_id"],
            "task_id": row["task_id"],
            "author": row["author"],
            "content_hash": row["content_hash"],
            "submitted_at": row["submitted_at"],
            "submission_method": row["submission_method"],
        }
        if include_content:
            result["content"] = row["content"]
        return result

    def list_positions(self, task_id: str, viewer: str) -> list[dict[str, Any]]:
        with self._connection() as db:
            task = self._task_row(db, task_id)
            revealed = task["status"] in self.TERMINAL_VISIBLE_STATES
            rows = db.execute("SELECT * FROM positions WHERE task_id = ? ORDER BY submitted_at, position_id", (task_id,)).fetchall()
            visible = []
            for row in rows:
                may_read = task["mode"] == "open" or revealed or row["author"] == viewer
                visible.append(self._position_dict(row, include_content=may_read))
            return visible

    def close_collection(self, task_id: str, actor: str = "human", note: str = "manual close") -> dict[str, Any]:
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if task["status"] != "collecting":
                raise Conflict(f"cannot close collection while task is {task['status']}")
            count = db.execute("SELECT COUNT(*) FROM positions WHERE task_id = ?", (task_id,)).fetchone()[0]
            if count == 0:
                raise Conflict("cannot close an empty collection")
            now = _now()
            db.execute("UPDATE tasks SET status = 'ready_to_reveal', updated_at = ? WHERE task_id = ?", (now, task_id))
            self._append_event(db, "collection_closed", task_id, actor, {"note": note, "position_count": count})
            return self._task_dict(self._task_row(db, task_id))

    def reveal(self, task_id: str, actor: str = "human") -> dict[str, Any]:
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if task["status"] != "ready_to_reveal":
                raise Conflict("collection must be complete or manually closed before reveal")
            now = _now()
            db.execute("UPDATE tasks SET status = 'revealed', revealed_at = ?, updated_at = ? WHERE task_id = ?", (now, now, task_id))
            self._append_event(db, "positions_revealed", task_id, actor, {"position_count": db.execute("SELECT COUNT(*) FROM positions WHERE task_id = ?", (task_id,)).fetchone()[0]})
            return self._task_dict(self._task_row(db, task_id))

    def record_decision(
        self,
        task_id: str,
        choice: str,
        rationale: str,
        supporting_position_ids: list[str] | None = None,
        considered_not_chosen_position_ids: list[str] | None = None,
        requires_approval: bool = False,
        actor: str = "human",
    ) -> dict[str, Any]:
        choice, rationale = choice.strip(), rationale.strip()
        if not choice or not rationale:
            raise ValueError("choice and rationale are required")
        supporting = list(dict.fromkeys(self._string_list(supporting_position_ids, "supporting_position_ids")))
        dissent = list(dict.fromkeys(self._string_list(considered_not_chosen_position_ids, "considered_not_chosen_position_ids")))
        if set(supporting) & set(dissent):
            raise ValueError("a position cannot be both supporting and considered-not-chosen")
        decision_id, now = _id("dec"), _now()
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if task["status"] not in {"revealed", "changes_requested"}:
                raise Conflict(f"a decision cannot be recorded while task is {task['status']}")
            linked = set(supporting + dissent)
            if linked:
                placeholders = ",".join("?" for _ in linked)
                found = db.execute(
                    f"SELECT position_id FROM positions WHERE task_id = ? AND position_id IN ({placeholders})",
                    [task_id, *linked],
                ).fetchall()
                if {r[0] for r in found} != linked:
                    raise ValueError("every linked position must belong to this task")
            status = "awaiting_approval" if requires_approval else "decided"
            db.execute(
                """INSERT INTO decisions(decision_id, task_id, choice, rationale, supporting_position_ids_json,
                   considered_not_chosen_ids_json, requires_approval, status, supersedes_decision_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, task_id, choice, rationale, _json(supporting), _json(dissent), int(requires_approval), status,
                 task["current_decision_id"], now),
            )
            db.execute(
                "UPDATE tasks SET status = ?, current_decision_id = ?, updated_at = ? WHERE task_id = ?",
                (status, decision_id, now, task_id),
            )
            self._append_event(db, "decision_recorded", task_id, actor, {
                "decision_id": decision_id,
                "choice": choice,
                "rationale": rationale,
                "supporting_position_ids": supporting,
                "considered_not_chosen_position_ids": dissent,
                "requires_approval": bool(requires_approval),
                "status": status,
                "supersedes_decision_id": task["current_decision_id"],
            })
            return self._decision_dict(db.execute("SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone())

    @staticmethod
    def _decision_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "decision_id": row["decision_id"],
            "task_id": row["task_id"],
            "choice": row["choice"],
            "rationale": row["rationale"],
            "supporting_position_ids": json.loads(row["supporting_position_ids_json"]),
            "considered_not_chosen_position_ids": json.loads(row["considered_not_chosen_ids_json"]),
            "requires_approval": bool(row["requires_approval"]),
            "status": row["status"],
            "supersedes_decision_id": row["supersedes_decision_id"],
            "created_at": row["created_at"],
        }

    def get_current_decision(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                return None
            row = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            return self._decision_dict(row)

    def record_approval(self, task_id: str, action: str, note: str, actor: str = "human") -> dict[str, Any]:
        if actor != "human":
            raise Forbidden("only the human principal may record an approval")
        if action not in {"approve", "reject", "request_changes"}:
            raise ValueError("action must be approve, reject, or request_changes")
        note = note.strip()
        if not note:
            raise ValueError("an approval note is required")
        approval_id, now = _id("approval"), _now()
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                raise Conflict("there is no decision to approve")
            decision = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            if not decision["requires_approval"] or decision["status"] != "awaiting_approval":
                raise Conflict("the current decision is not awaiting approval")
            next_status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}[action]
            db.execute(
                "INSERT INTO approvals(approval_id, decision_id, actor, action, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (approval_id, decision["decision_id"], actor, action, note, now),
            )
            db.execute("UPDATE decisions SET status = ? WHERE decision_id = ?", (next_status, decision["decision_id"]))
            db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?", (next_status, now, task_id))
            self._append_event(db, "approval_recorded", task_id, actor, {
                "approval_id": approval_id,
                "decision_id": decision["decision_id"],
                "action": action,
                "note": note,
                "resulting_status": next_status,
            })
            row = db.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            return dict(row)

    def authorize_action(self, task_id: str, action_name: str, actor: str = "human") -> dict[str, Any]:
        action_name = action_name.strip()
        if not action_name:
            raise ValueError("action_name is required")
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                raise Conflict("no decision exists for this task")
            decision = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            if decision["status"] in {"rejected", "changes_requested"}:
                raise Conflict(f"current decision is {decision['status']}")
            if decision["requires_approval"] and decision["status"] != "approved":
                raise ApprovalRequired("human approval is required before this action")
            if task["status"] not in {"decided", "approved", "implemented"}:
                raise Conflict(f"task is not in an actionable state: {task['status']}")
            event = self._append_event(db, "action_authorized", task_id, actor, {
                "action_name": action_name,
                "decision_id": decision["decision_id"],
