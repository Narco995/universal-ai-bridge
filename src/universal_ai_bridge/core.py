from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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


class Unauthorized(BridgeError):
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
        raw_database = str(database)
        if raw_database == ":memory:":
            raise ValueError("a persistent SQLite file path is required; :memory: is not supported across Bridge connections")
        self.database = str(Path(raw_database).expanduser().resolve())
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS principals (
                    principal_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('owner', 'participant')),
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, name, role)
                );
                CREATE INDEX IF NOT EXISTS idx_principals_task ON principals(task_id);
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
                    action_name TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
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
            # Lightweight forward-compatible migration for databases created by
            # the first v0 draft, before approvals were action-scoped.
            approval_columns = {row["name"] for row in db.execute("PRAGMA table_info(approvals)").fetchall()}
            for column in ("action_name", "target", "scope", "expires_at"):
                if column not in approval_columns:
                    db.execute(f"ALTER TABLE approvals ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

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
        if not isinstance(objective, str):
            raise ValueError("objective must be a string")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        objective = objective.strip()
        criteria_input = self._string_list(acceptance_criteria, "acceptance_criteria")
        authors_input = self._string_list(required_authors, "required_authors")
        criteria = [item.strip() for item in criteria_input if item.strip()]
        authors = list(dict.fromkeys(a.strip() for a in authors_input if a.strip()))
        if not objective:
            raise ValueError("objective is required")
        if not criteria:
            raise ValueError("at least one acceptance criterion is required")
        if not isinstance(mode, str) or mode not in {"independent", "open"}:
            raise ValueError("mode must be 'independent' or 'open'")
        task_id, now = _id("task"), _now()
        owner_token = secrets.token_urlsafe(32)
        participant_tokens = {author: secrets.token_urlsafe(32) for author in authors}
        credentials = {"owner_token": owner_token, "participant_tokens": participant_tokens}
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
            owner_id = _id("principal")
            db.execute(
                "INSERT INTO principals(principal_id, task_id, name, role, token_hash, created_at) VALUES (?, ?, ?, 'owner', ?, ?)",
                (owner_id, task_id, "human", hashlib.sha256(owner_token.encode("utf-8")).hexdigest(), now),
            )
            self._append_event(db, "principal_issued", task_id, actor, {
                "principal_id": owner_id, "name": "human", "role": "owner",
            })
            for author, token in participant_tokens.items():
                principal_id = _id("principal")
                db.execute(
                    "INSERT INTO principals(principal_id, task_id, name, role, token_hash, created_at) VALUES (?, ?, ?, 'participant', ?, ?)",
                    (principal_id, task_id, author, hashlib.sha256(token.encode("utf-8")).hexdigest(), now),
                )
                self._append_event(db, "principal_issued", task_id, actor, {
                    "principal_id": principal_id, "name": author, "role": "participant",
                })
            row = self._task_row(db, task_id)
            result = self._task_dict(row)
            # Secrets are returned once to the task creator and are never stored in events.
            result["credentials"] = credentials
            return result

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connection() as db:
            return self._task_dict(self._task_row(db, task_id))

    def authenticate_principal(self, task_id: str, token: str) -> dict[str, str]:
        """Resolve a task-scoped bearer token without trusting caller-supplied identity headers."""
        if not isinstance(token, str) or not token.strip():
            raise Unauthorized("a valid task-scoped bearer token is required")
        digest = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
        with self._connection() as db:
            self._task_row(db, task_id)
            rows = db.execute(
                "SELECT principal_id, name, role, token_hash FROM principals WHERE task_id = ?",
                (task_id,),
            ).fetchall()
            for row in rows:
                if hmac.compare_digest(row["token_hash"], digest):
                    return {"principal_id": row["principal_id"], "name": row["name"], "role": row["role"]}
        raise Unauthorized("invalid task-scoped bearer token")

    def submit_position(self, task_id: str, author: str, content: str, actor: str = "human") -> dict[str, Any]:
        if not isinstance(author, str) or not isinstance(content, str):
            raise ValueError("author and content must be strings")
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
        if not isinstance(note, str):
            raise ValueError("collection close note must be a string")
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
        if not isinstance(choice, str) or not isinstance(rationale, str):
            raise ValueError("choice and rationale must be strings")
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a boolean")
        choice, rationale = choice.strip(), rationale.strip()
        if not choice or not rationale:
            raise ValueError("choice and rationale are required")
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a boolean")
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

    def record_approval(
        self,
        task_id: str,
        action: str,
        note: str,
        actor: str = "human",
        action_name: str = "",
        target: str = "",
        scope: str = "",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        if actor != "human":
            raise Forbidden("only the human principal may record an approval")
        if not isinstance(action, str) or action not in {"approve", "reject", "request_changes"}:
            raise ValueError("action must be approve, reject, or request_changes")
        if not all(isinstance(value, str) for value in (note, action_name, target, scope)):
            raise ValueError("approval note, action_name, target, and scope must be strings")
        note, action_name, target, scope = note.strip(), action_name.strip(), target.strip(), scope.strip()
        if not note or not action_name or not target or not scope:
            raise ValueError("approval requires a note and an exact action_name, target, and scope")
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="microseconds")
        if expires_at is None or (isinstance(expires_at, str) and not expires_at.strip()):
            expires_dt = now_dt + timedelta(minutes=15)
        else:
            if not isinstance(expires_at, str):
                raise ValueError("expires_at must be an ISO-8601 timestamp string")
            try:
                expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("expires_at must be a valid ISO-8601 timestamp") from exc
            if expires_dt.tzinfo is None:
                raise ValueError("expires_at must include a timezone")
            expires_dt = expires_dt.astimezone(timezone.utc)
        if expires_dt <= now_dt:
            raise ValueError("approval expiry must be in the future")
        normalized_expiry = expires_dt.isoformat(timespec="microseconds")
        approval_id = _id("approval")
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                raise Conflict("there is no decision to approve")
            decision = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            if decision["status"] in {"rejected", "changes_requested"}:
                raise Conflict(f"the current decision is {decision['status']}")
            if action in {"reject", "request_changes"} and decision["status"] != "awaiting_approval":
                raise Conflict("reject/request_changes requires a decision awaiting approval")
            if action == "approve" and decision["status"] not in {"awaiting_approval", "decided", "approved"}:
                raise Conflict(f"the current decision cannot be approved while {decision['status']}")
            next_status = decision["status"]
            if decision["requires_approval"]:
                next_status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}[action]
            db.execute(
                """INSERT INTO approvals(approval_id, decision_id, actor, action, action_name, target, scope, expires_at, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (approval_id, decision["decision_id"], actor, action, action_name, target, scope, normalized_expiry, note, now),
            )
            if next_status != decision["status"]:
                db.execute("UPDATE decisions SET status = ? WHERE decision_id = ?", (next_status, decision["decision_id"]))
                db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?", (next_status, now, task_id))
            self._append_event(db, "approval_recorded", task_id, actor, {
                "approval_id": approval_id,
                "decision_id": decision["decision_id"],
                "action": action,
                "action_name": action_name,
                "target": target,
                "scope": scope,
                "expires_at": normalized_expiry,
                "note": note,
                "resulting_status": next_status,
            })
            row = db.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            return dict(row)

    def authorize_action(
        self,
        task_id: str,
        action_name: str,
        actor: str = "human",
        target: str = "",
        scope: str = "",
    ) -> dict[str, Any]:
        if not all(isinstance(value, str) for value in (action_name, target, scope)):
            raise ValueError("action_name, target, and scope must be strings")
        action_name, target, scope = action_name.strip(), target.strip(), scope.strip()
        if not action_name or not target or not scope:
            raise ValueError("action_name, target, and scope are required")
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                raise Conflict("no decision exists for this task")
            decision = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            if decision["status"] in {"rejected", "changes_requested"}:
                raise Conflict(f"current decision is {decision['status']}")
            # This endpoint is an authorization boundary, not a read-operation classifier.
            # Every caller reaching it must present an exact, unexpired human approval.
            approval_required = True
            if approval_required:
                approval = db.execute(
                    """SELECT approval_id FROM approvals
                       WHERE decision_id = ? AND action = 'approve'
                         AND action_name = ? AND target = ? AND scope = ?
                         AND expires_at > ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (decision["decision_id"], action_name, target, scope, _now()),
                ).fetchone()
                if approval is None:
                    raise ApprovalRequired(
                        "human approval is required for this exact action, target, and scope"
                    )
                if decision["requires_approval"] and decision["status"] != "approved":
                    raise ApprovalRequired("the current decision has not been approved")
            if task["status"] not in {"decided", "approved", "implemented"}:
                raise Conflict(f"task is not in an actionable state: {task['status']}")
            event = self._append_event(db, "action_authorized", task_id, actor, {
                "action_name": action_name,
                "target": target,
                "scope": scope,
                "decision_id": decision["decision_id"],
                "approval_required": approval_required,
                "authorization_only": True,
                "does_not_execute_side_effect": True,
            })
            return {
                "authorized": True,
                "action_name": action_name,
                "target": target,
                "scope": scope,
                "event_id": event["event_id"],
                "executed": False,
            }

    def attach_artifact(
        self,
        task_id: str,
        kind: str,
        uri: str,
        sha256: str | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        if not isinstance(kind, str) or not isinstance(uri, str):
            raise ValueError("artifact kind and uri must be strings")
        if not isinstance(kind, str) or not isinstance(uri, str):
            raise ValueError("artifact kind and uri must be strings")
        kind, uri = kind.strip(), uri.strip()
        if not kind or not uri:
            raise ValueError("artifact kind and uri are required")
        if sha256 is not None and (not isinstance(sha256, str) or len(sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha256)):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        if sha256 is not None:
            sha256 = sha256.lower()
        if sha256 is not None:
            if not isinstance(sha256, str) or len(sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha256):
                raise ValueError("sha256 must be a 64-character hexadecimal digest")
        artifact_id, now = _id("artifact"), _now()
        with self._transaction() as db:
            task = self._task_row(db, task_id)
            if not task["current_decision_id"]:
                raise Conflict("no decision exists for this task")
            decision = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (task["current_decision_id"],)).fetchone()
            if decision["requires_approval"]:
                active_approval = db.execute(
                    "SELECT approval_id FROM approvals WHERE decision_id = ? AND action = 'approve' AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                    (decision["decision_id"], _now()),
                ).fetchone()
                if decision["status"] != "approved" or active_approval is None:
                    raise ApprovalRequired("a valid, unexpired human approval is required before attaching an implementation artifact")
            if decision["status"] in {"rejected", "changes_requested"}:
                raise Conflict(f"current decision is {decision['status']}")
            db.execute(
                "INSERT INTO artifacts(artifact_id, task_id, kind, uri, sha256, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (artifact_id, task_id, kind, uri, sha256, now),
            )
            db.execute("UPDATE tasks SET status = 'implemented', updated_at = ? WHERE task_id = ?", (now, task_id))
            self._append_event(db, "artifact_attached", task_id, actor, {
                "artifact_id": artifact_id, "kind": kind, "uri": uri, "sha256": sha256,
            })
            return dict(db.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone())

    def export_timeline(self, task_id: str, viewer: str = "human") -> dict[str, Any]:
        with self._connection() as db:
            task_row = self._task_row(db, task_id)
            task = self._task_dict(task_row)
            revealed = task["status"] in self.TERMINAL_VISIBLE_STATES
            position_rows = db.execute("SELECT * FROM positions WHERE task_id = ? ORDER BY submitted_at, position_id", (task_id,)).fetchall()
            positions = [
                self._position_dict(row, include_content=(task["mode"] == "open" or revealed or row["author"] == viewer))
                for row in position_rows
            ]
            decisions = [self._decision_dict(row) for row in db.execute("SELECT * FROM decisions WHERE task_id = ? ORDER BY created_at, decision_id", (task_id,)).fetchall()]
            approvals = [dict(row) for row in db.execute(
                "SELECT a.* FROM approvals a JOIN decisions d ON d.decision_id = a.decision_id WHERE d.task_id = ? ORDER BY a.created_at, a.approval_id",
                (task_id,),
            ).fetchall()]
            artifacts = [dict(row) for row in db.execute("SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at, artifact_id", (task_id,)).fetchall()]
            event_rows = db.execute("SELECT * FROM events WHERE task_id = ? ORDER BY event_id", (task_id,)).fetchall()
            events = []
            for row in event_rows:
                payload = json.loads(row["payload_json"])
                if row["event_type"] == "position_submitted" and task["mode"] == "independent" and not revealed and payload.get("author") != viewer:
                    payload.pop("content", None)
                    payload["content_redacted"] = True
                events.append({
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "task_id": row["task_id"],
                    "actor": row["actor"],
                    "payload": payload,
                    "occurred_at": row["occurred_at"],
                    "previous_hash": row["previous_hash"],
                    "event_hash": row["event_hash"],
                })
            return {
                "task": task,
                "positions": positions,
                "decisions": decisions,
                "approvals": approvals,
                "artifacts": artifacts,
                "events": events,
                "provenance": {
                    "agent_connections": "not_connected",
                    "position_submission": "manual_user_relay",
                    "independent_analysis": "depends_on_separate_sessions_and_no_cross_sharing_before_reveal",
                },
            }

    def verify_event_chain(self) -> dict[str, Any]:
        with self._connection() as db:
            rows = db.execute("SELECT * FROM events ORDER BY event_id").fetchall()
            previous_hash = "0" * 64
            for row in rows:
                if row["previous_hash"] != previous_hash:
                    return {"valid": False, "event_id": row["event_id"], "reason": "previous_hash_mismatch"}
                canonical = _json({
                    "event_type": row["event_type"],
                    "task_id": row["task_id"],
                    "actor": row["actor"],
                    "payload_json": row["payload_json"],
                    "occurred_at": row["occurred_at"],
                    "previous_hash": row["previous_hash"],
                })
                expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if row["event_hash"] != expected:
                    return {"valid": False, "event_id": row["event_id"], "reason": "event_hash_mismatch"}
                previous_hash = row["event_hash"]
            # Verify that queryable SQLite projections still agree with their source events.
            event_counts = {
                "tasks": sum(row["event_type"] == "task_created" for row in rows),
                "positions": sum(row["event_type"] == "position_submitted" for row in rows),
                "decisions": sum(row["event_type"] == "decision_recorded" for row in rows),
                "approvals": sum(row["event_type"] == "approval_recorded" for row in rows),
                "artifacts": sum(row["event_type"] == "artifact_attached" for row in rows),
                "principals": sum(row["event_type"] == "principal_issued" for row in rows),
            }
            for table, expected_count in event_counts.items():
                actual_count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if actual_count != expected_count:
                    return {
                        "valid": False,
                        "reason": "projection_count_mismatch",
                        "table": table,
                        "expected": expected_count,
                        "actual": actual_count,
                    }

            for event in rows:
                payload = json.loads(event["payload_json"])
                kind = event["event_type"]
                if kind == "task_created":
                    projection = db.execute("SELECT * FROM tasks WHERE task_id = ?", (event["task_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["objective"] == payload["objective"]
                        and json.loads(projection["acceptance_criteria_json"]) == payload["acceptance_criteria"]
                        and projection["mode"] == payload["mode"]
                        and json.loads(projection["required_authors_json"]) == payload["required_authors"]
                    )
                elif kind == "position_submitted":
                    projection = db.execute("SELECT * FROM positions WHERE position_id = ?", (payload["position_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["task_id"] == event["task_id"]
                        and projection["author"] == payload["author"]
                        and projection["content"] == payload["content"]
                        and projection["content_hash"] == payload["content_hash"]
                        and projection["submission_method"] == payload["submission_method"]
                    )
                elif kind == "decision_recorded":
                    projection = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (payload["decision_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["task_id"] == event["task_id"]
                        and projection["choice"] == payload["choice"]
                        and projection["rationale"] == payload["rationale"]
                        and json.loads(projection["supporting_position_ids_json"]) == payload["supporting_position_ids"]
                        and json.loads(projection["considered_not_chosen_ids_json"]) == payload["considered_not_chosen_position_ids"]
                        and bool(projection["requires_approval"]) == payload["requires_approval"]
                        and projection["supersedes_decision_id"] == payload["supersedes_decision_id"]
                    )
                elif kind == "approval_recorded":
                    projection = db.execute("SELECT * FROM approvals WHERE approval_id = ?", (payload["approval_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["decision_id"] == payload["decision_id"]
                        and projection["actor"] == event["actor"]
                        and projection["action"] == payload["action"]
                        and projection["action_name"] == payload.get("action_name", "")
                        and projection["target"] == payload.get("target", "")
                        and projection["scope"] == payload.get("scope", "")
                        and projection["expires_at"] == payload.get("expires_at", "")
                        and projection["note"] == payload["note"]
                    )
                elif kind == "artifact_attached":
                    projection = db.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (payload["artifact_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["task_id"] == event["task_id"]
                        and projection["kind"] == payload["kind"]
                        and projection["uri"] == payload["uri"]
                        and projection["sha256"] == payload["sha256"]
                    )
                elif kind == "principal_issued":
                    projection = db.execute("SELECT * FROM principals WHERE principal_id = ?", (payload["principal_id"],)).fetchone()
                    matches = projection is not None and (
                        projection["task_id"] == event["task_id"]
                        and projection["name"] == payload["name"]
                        and projection["role"] == payload["role"]
                        and bool(projection["token_hash"])
                    )
                else:
                    continue
                if not matches:
                    return {
                        "valid": False,
                        "event_id": event["event_id"],
                        "reason": "projection_mismatch",
                        "event_type": kind,
                    }
            # Reconstruct workflow state from events and compare mutable projections.
            task_states: dict[str, dict[str, Any]] = {}
            decision_states: dict[str, str] = {}
            for event in rows:
                kind = event["event_type"]
                payload = json.loads(event["payload_json"])
                task_id = event["task_id"]
                if kind == "task_created":
                    task_states[task_id] = {
                        "status": "collecting",
                        "current_decision_id": None,
                        "revealed": False,
                    }
                elif kind in {"collection_ready", "collection_closed"}:
                    task_states[task_id]["status"] = "ready_to_reveal"
                elif kind == "positions_revealed":
                    task_states[task_id]["status"] = "revealed"
                    task_states[task_id]["revealed"] = True
                elif kind == "decision_recorded":
                    decision_states[payload["decision_id"]] = payload["status"]
                    task_states[task_id]["status"] = payload["status"]
                    task_states[task_id]["current_decision_id"] = payload["decision_id"]
                elif kind == "approval_recorded":
                    decision_states[payload["decision_id"]] = payload["resulting_status"]
                    if task_states[task_id]["current_decision_id"] == payload["decision_id"]:
                        task_states[task_id]["status"] = payload["resulting_status"]
                elif kind == "artifact_attached":
                    task_states[task_id]["status"] = "implemented"

            for task_id, expected in task_states.items():
                projection = db.execute("SELECT status, current_decision_id, revealed_at FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
                if projection is None or projection["status"] != expected["status"] or projection["current_decision_id"] != expected["current_decision_id"] or bool(projection["revealed_at"]) != expected["revealed"]:
                    return {"valid": False, "reason": "task_state_projection_mismatch", "task_id": task_id}
            for decision_id, expected_status in decision_states.items():
                projection = db.execute("SELECT status FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
                if projection is None or projection["status"] != expected_status:
                    return {"valid": False, "reason": "decision_state_projection_mismatch", "decision_id": decision_id}

            return {"valid": True, "events_checked": len(rows), "head_hash": previous_hash, "projections_verified": True}

    def markdown_export(self, task_id: str, viewer: str = "human") -> str:
        data = self.export_timeline(task_id, viewer=viewer)
        task = data["task"]
        lines = [f"# {task['objective']}", "", f"- Task: `{task['task_id']}`", f"- Mode: `{task['mode']}`", f"- Status: `{task['status']}`", "", "## Acceptance criteria"]
        lines.extend(f"- {item}" for item in task["acceptance_criteria"])
        lines += ["", "## Positions"]
        for position in data["positions"]:
            lines.append(f"### {position['author']} — `{position['position_id']}`")
            lines.append(position.get("content", "[sealed until reveal]"))
            lines.append("")
        lines.append("## Decisions")
        for decision in data["decisions"]:
            lines += [f"### {decision['choice']}", decision["rationale"], f"- Status: `{decision['status']}`", f"- Supporting: {', '.join(decision['supporting_position_ids']) or 'none'}", f"- Considered but not chosen: {', '.join(decision['considered_not_chosen_position_ids']) or 'none'}", ""]
        lines.append("## Approvals")
        for approval in data["approvals"]:
            lines.append(f"- {approval['action']} by {approval['actor']}: {approval['note']}")
        lines += ["", "## Artifacts"]
        for artifact in data["artifacts"]:
            lines.append(f"- {artifact['kind']}: {artifact['uri']} (SHA-256: {artifact['sha256'] or 'not supplied'})")
        lines += ["", "## Provenance", f"- Agent connections: `{data['provenance']['agent_connections']}`", f"- Position submission: `{data['provenance']['position_submission']}`", f"- Independence: `{data['provenance']['independent_analysis']}`", ""]
        return "\n".join(lines)
