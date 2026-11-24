import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_ai_bridge import (
    ApprovalRequired,
    BridgeService,
    Conflict,
    Forbidden,
    Unauthorized,
)


class BridgeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = BridgeService(Path(self.tmp.name) / "bridge.sqlite3")
        self.task = self.service.create_task(
            "Choose a safe persistence design",
            ["Preserve dissent", "Block unapproved consequential actions"],
            mode="independent",
            required_authors=["claude", "gpt"],
        )
        self.task_id = self.task["task_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_manual_execution_mode_is_separate_and_persisted(self):
        auto_task = self.service.create_task(
            "Record autonomous execution preference",
            ["Keep execution policy separate from collection policy"],
            mode="independent",
            execution_mode="auto",
        )
        self.assertEqual(auto_task["mode"], "independent")
        self.assertEqual(auto_task["execution_mode"], "auto")
        self.assertEqual(self.service.get_task(auto_task["task_id"])["execution_mode"], "auto")
        self.assertIn("Execution mode: `auto`", self.service.markdown_export(auto_task["task_id"]))
        self.assertTrue(self.service.verify_event_chain()["valid"])

        manual_task = self.service.create_task(
            "Record manual execution preference",
            ["Default to human checkpoints"],
            mode="open",
        )
        self.assertEqual(manual_task["execution_mode"], "manual")
        with self.assertRaises(ValueError):
            self.service.create_task(
                "Reject unknown execution policy",
                ["Only supported modes are accepted"],
                execution_mode="unattended",
            )

    def test_sealed_positions_are_hidden_until_reveal(self):
        claude = self.service.submit_position(self.task_id, "claude", "Use append-only SQLite events")
        self.service.submit_position(self.task_id, "gpt", "Use mutable JSON snapshots")
        gpt_view = self.service.list_positions(self.task_id, viewer="gpt")
        self.assertEqual(len(gpt_view), 2)
        self.assertIn("content", next(p for p in gpt_view if p["author"] == "gpt"))
        self.assertNotIn("content", next(p for p in gpt_view if p["author"] == "claude"))
        self.assertEqual(self.service.get_task(self.task_id)["status"], "ready_to_reveal")
        self.service.reveal(self.task_id)
        all_positions = self.service.list_positions(self.task_id, viewer="gpt")
        self.assertIn("content", next(p for p in all_positions if p["author"] == "claude"))
        self.assertEqual(claude["submission_method"], "manual")

    def test_rejected_objection_is_preserved_and_exported(self):
        p1 = self.service.submit_position(self.task_id, "claude", "Append-only events with replay")
        p2 = self.service.submit_position(self.task_id, "gpt", "Mutable snapshots are simpler")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(
            self.task_id,
            "Append-only SQLite events",
            "Replay and immutable audit history are required for reproducibility.",
            supporting_position_ids=[p1["position_id"]],
            considered_not_chosen_position_ids=[p2["position_id"]],
        )
        exported = self.service.export_timeline(self.task_id)
        self.assertIn(p2["position_id"], exported["decisions"][0]["considered_not_chosen_position_ids"])
        self.assertEqual(len(exported["positions"]), 2)
        self.assertEqual(exported["task"]["status"], "decided")
        self.assertEqual(decision["status"], "decided")

    def test_export_reproduces_complete_timeline(self):
        p1 = self.service.submit_position(self.task_id, "claude", "Proposal A")
        self.service.submit_position(self.task_id, "gpt", "Proposal B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(self.task_id, "A", "A meets the criteria", [p1["position_id"]], [], True)
        action = "modify_shared_infrastructure"
        target = "repository/main"
        scope = "change collaboration workflow"
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.service.record_approval(
            self.task_id, "approve", "Approved the decision",
            action_name="decision_acceptance", target=self.task_id, scope=decision["decision_id"],
        )
        self.service.record_approval(
            self.task_id, "approve", "Approved the exact implementation action",
            action_name=action, target=target, scope=scope,
        )
        self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.service.attach_artifact(self.task_id, "commit", "https://example.invalid/commit/abc", "a" * 64)
        exported = self.service.export_timeline(self.task_id)
        types = [event["event_type"] for event in exported["events"]]
        for expected in ["task_created", "position_submitted", "positions_revealed", "decision_recorded", "approval_recorded", "action_authorized", "artifact_attached"]:
            self.assertIn(expected, types)
        self.assertEqual(exported["task"]["status"], "implemented")
        self.assertEqual(exported["approvals"][0]["action"], "approve")
        self.assertEqual(exported["artifacts"][0]["kind"], "commit")
        self.assertEqual(exported["provenance"]["agent_connections"], "not_connected")
        self.assertTrue(self.service.verify_event_chain()["valid"])

    def test_human_approval_gate_blocks_then_unblocks(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(self.task_id, "A", "A is safer", requires_approval=True)
        self.assertEqual(decision["status"], "awaiting_approval")
        action = "change_security_policy"
        target = "bridge/security-policy"
        scope = "modify approval enforcement rules"
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        with self.assertRaises(ApprovalRequired):
            self.service.attach_artifact(self.task_id, "commit", "https://example.invalid/commit/blocked")
        with self.assertRaises(Forbidden):
            self.service.record_approval(
                self.task_id, "approve", "not the principal", actor="gpt",
                action_name="decision_acceptance", target=self.task_id, scope=decision["decision_id"],
            )
        self.service.record_approval(
            self.task_id, "approve", "Human principal accepted the decision", actor="human",
            action_name="decision_acceptance", target=self.task_id, scope=decision["decision_id"],
        )
        self.service.record_approval(
            self.task_id, "approve", "Human principal approved the exact action", actor="human",
            action_name=action, target=target, scope=scope,
        )
        result = self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.assertTrue(result["authorized"])
        self.assertFalse(result["executed"])

    def test_high_impact_action_requires_scoped_approval_even_when_decision_flag_is_false(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Decision accepted without a global approval flag")
        action = "deploy"
        target = "production/api"
        scope = "release version 1.2.3"
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.service.record_approval(
            self.task_id, "approve", "Approved for this exact release",
            action_name=action, target=target, scope=scope,
        )
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target="staging/api", scope=scope)
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target=target, scope="release version 1.2.4")
        result = self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.assertTrue(result["authorized"])
        self.assertEqual(result["target"], target)
        self.assertEqual(result["scope"], scope)

    def test_authorization_endpoint_never_trusts_a_caller_selected_low_risk_label(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Read-only actions use GET routes, not this gate")
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(
                self.task_id, "export", target="production/deploy", scope="write release 1.0"
            )
        self.service.record_approval(
            self.task_id, "approve", "Approved exact operation",
            action_name="export", target="production/deploy", scope="write release 1.0",
        )
        result = self.service.authorize_action(
            self.task_id, "export", target="production/deploy", scope="write release 1.0"
        )
        self.assertTrue(result["authorized"])
        self.assertFalse(result["executed"])

    def test_approval_expiry_is_enforced(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Accepted")
        approval = self.service.record_approval(
            self.task_id, "approve", "Short-lived authorization",
            action_name="deploy", target="staging", scope="release 1.0",
        )
        self.assertTrue(approval["expires_at"])
        with sqlite3.connect(self.service.database) as db:
            db.execute(
                "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
                ("2000-01-01T00:00:00.000000+00:00", approval["approval_id"]),
            )
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(
                self.task_id, "deploy", target="staging", scope="release 1.0"
            )
        integrity = self.service.verify_event_chain()
        self.assertFalse(integrity["valid"])
        self.assertEqual(integrity["reason"], "projection_mismatch")

    def test_task_and_decision_state_projection_tampering_is_detected(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(self.task_id, "A", "Evidence-backed choice")
        with sqlite3.connect(self.service.database) as db:
            db.execute("UPDATE tasks SET status = 'implemented' WHERE task_id = ?", (self.task_id,))
            db.execute("UPDATE decisions SET status = 'approved' WHERE decision_id = ?", (decision["decision_id"],))
        integrity = self.service.verify_event_chain()
        self.assertFalse(integrity["valid"])
        self.assertEqual(integrity["reason"], "task_state_projection_mismatch")

    def test_decision_state_tampering_is_detected_when_task_status_is_consistent(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(self.task_id, "A", "Evidence-backed choice")
        with sqlite3.connect(self.service.database) as db:
            db.execute("UPDATE decisions SET status = 'approved' WHERE decision_id = ?", (decision["decision_id"],))
        integrity = self.service.verify_event_chain()
        self.assertFalse(integrity["valid"])
        self.assertEqual(integrity["reason"], "decision_state_projection_mismatch")

    def test_open_task_can_issue_participant_credentials_after_creation(self):
        task = self.service.create_task("Open collaboration", ["Allow dynamic contributors"], mode="open")
        issued = self.service.issue_participant(task["task_id"], "grok")
        principal = self.service.authenticate_principal(task["task_id"], issued["token"])
        self.assertEqual(principal["name"], "grok")
        self.assertEqual(principal["role"], "participant")
        with self.assertRaises(Conflict):
            self.service.issue_participant(task["task_id"], "grok")

    def test_task_principal_credentials_are_task_scoped_and_secrets_are_not_logged(self):
        credentials = self.task["credentials"]
        participant = credentials["participant_tokens"]["claude"]
        principal = self.service.authenticate_principal(self.task_id, participant)
        self.assertEqual(principal["name"], "claude")
        self.assertEqual(principal["role"], "participant")
        owner = self.service.authenticate_principal(self.task_id, credentials["owner_token"])
        self.assertEqual(owner["role"], "owner")
        with self.assertRaises(Unauthorized):
            self.service.authenticate_principal(self.task_id, "not-a-valid-token")
        other_task = self.service.create_task("Another task", ["Independent scope"])
        with self.assertRaises(Unauthorized):
            self.service.authenticate_principal(other_task["task_id"], participant)
        exported = json.dumps(self.service.export_timeline(self.task_id))
        self.assertNotIn(participant, exported)
        self.assertNotIn(credentials["owner_token"], exported)

    def test_expired_decision_acceptance_blocks_action_even_when_action_approval_is_live(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(
            self.task_id, "A", "Decision requires separate acceptance", requires_approval=True
        )
        decision_approval = self.service.record_approval(
            self.task_id, "approve", "Accepted this decision",
            action_name="decision_acceptance", target=self.task_id, scope=decision["decision_id"],
        )
        self.service.record_approval(
            self.task_id, "approve", "Approved exact action",
            action_name="deploy", target="production", scope="release 2.0",
        )
        with sqlite3.connect(self.service.database) as db:
            db.execute(
                "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
                ("2000-01-01T00:00:00.000000+00:00", decision_approval["approval_id"]),
            )
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(
                self.task_id, "deploy", target="production", scope="release 2.0"
            )

    def test_expired_decision_approval_cannot_attach_artifact(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        decision = self.service.record_decision(self.task_id, "A", "Decision requires approval", requires_approval=True)
        approval = self.service.record_approval(
            self.task_id, "approve", "Short-lived decision approval",
            action_name="decision_acceptance", target=self.task_id, scope=decision["decision_id"],
        )
        with sqlite3.connect(self.service.database) as db:
            db.execute(
                "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
                ("2000-01-01T00:00:00.000000+00:00", approval["approval_id"]),
            )
        with self.assertRaises(ApprovalRequired):
            self.service.attach_artifact(
                self.task_id, "commit", "https://example.invalid/commit/expired"
            )

    def test_principal_token_hash_tampering_is_detected(self):
        token = self.task["credentials"]["participant_tokens"]["claude"]
        principal = self.service.authenticate_principal(self.task_id, token)
        with sqlite3.connect(self.service.database) as db:
            db.execute(
                "UPDATE principals SET token_hash = ? WHERE principal_id = ?",
                ("f" * 64, principal["principal_id"]),
            )
        integrity = self.service.verify_event_chain()
        self.assertFalse(integrity["valid"])
        self.assertEqual(integrity["reason"], "projection_mismatch")
        self.assertEqual(integrity["event_type"], "principal_issued")

    def test_action_approval_alone_cannot_attach_decision_gated_artifact(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(
            self.task_id, "A", "Requires decision acceptance", requires_approval=True
        )
        self.service.record_approval(
            self.task_id, "approve", "Approved only the deployment",
            action_name="deploy", target="production", scope="release 3.0",
        )
        with self.assertRaises(ApprovalRequired):
            self.service.attach_artifact(
                self.task_id, "commit", "https://example.invalid/commit/not-yet-approved"
            )

    def test_projection_tampering_is_detected(self):
        self.service.submit_position(self.task_id, "claude", "Original position")
        with sqlite3.connect(self.service.database) as db:
            db.execute(
                "UPDATE positions SET content = ? WHERE task_id = ?",
                ("tampered position", self.task_id),
            )
        integrity = self.service.verify_event_chain()
        self.assertFalse(integrity["valid"])
        self.assertEqual(integrity["reason"], "projection_mismatch")

    def test_expired_approval_cannot_be_created(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Accepted")
        with self.assertRaises(ValueError):
            self.service.record_approval(
                self.task_id, "approve", "Expired",
                action_name="deploy", target="production", scope="release 1.0",
                expires_at="2000-01-01T00:00:00Z",
            )

    def test_tilde_database_path_is_expanded(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}):
            service = BridgeService("~/bridge-test.sqlite3")
            self.assertEqual(service.database, str(Path(home) / "bridge-test.sqlite3"))

    def test_core_rejects_non_boolean_approval_flag(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        with self.assertRaises(TypeError):
            self.service.record_decision(
                self.task_id, "A", "Bad flag", requires_approval="false"
            )

    def test_artifact_sha256_must_be_a_hex_digest(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Accepted")
        with self.assertRaises(ValueError):
            self.service.attach_artifact(
                self.task_id, "commit", "https://example.invalid/commit/abc", "not-a-digest"
            )

    def test_legacy_approval_schema_is_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(database) as db:
                db.execute(
                    """CREATE TABLE tasks (
                        task_id TEXT PRIMARY KEY,
                        objective TEXT NOT NULL,
                        acceptance_criteria_json TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        required_authors_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        revealed_at TEXT,
                        current_decision_id TEXT
                    )"""
                )
                db.execute(
                    """INSERT INTO tasks(
                        task_id, objective, acceptance_criteria_json, mode,
                        required_authors_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("legacy-task", "Legacy task", '["migrated"]', "independent", "[]", "collecting", "2026-01-01", "2026-01-01"),
                )
                db.execute(
                    """CREATE TABLE approvals (
                        approval_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        action TEXT NOT NULL,
                        note TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )
            BridgeService(database)
            with sqlite3.connect(database) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(approvals)")}
            self.assertTrue({"action_name", "target", "scope", "expires_at"}.issubset(columns))
            with sqlite3.connect(database) as db:
                task_columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
            self.assertIn("execution_mode", task_columns)
            self.assertEqual(BridgeService(database).get_task("legacy-task")["execution_mode"], "manual")

    def test_export_redacts_other_authors_before_reveal(self):
        self.service.submit_position(self.task_id, "claude", "Private initial view A")
        self.service.submit_position(self.task_id, "gpt", "Private initial view B")
        exported = self.service.export_timeline(self.task_id, viewer="gpt")
        claude_event = next(e for e in exported["events"] if e["event_type"] == "position_submitted" and e["payload"]["author"] == "claude")
        self.assertNotIn("content", claude_event["payload"])
        self.assertTrue(claude_event["payload"]["content_redacted"])
        self.assertNotIn("content", next(p for p in exported["positions"] if p["author"] == "claude"))

    def test_open_mode_exposes_positions_without_reveal(self):
        task = self.service.create_task("Open collaboration", ["Share notes immediately"], mode="open")
        self.service.submit_position(task["task_id"], "claude", "Visible note")
        position = self.service.list_positions(task["task_id"], viewer="gpt")[0]
        self.assertEqual(position["content"], "Visible note")

    def test_duplicate_author_submission_is_rejected(self):
        self.service.submit_position(self.task_id, "claude", "First submission")
        with self.assertRaises(Conflict):
            self.service.submit_position(self.task_id, "claude", "Replacement submission")

    def test_event_log_is_append_only(self):
        self.service.submit_position(self.task_id, "claude", "An independent view")
        import sqlite3
        with sqlite3.connect(self.service.database) as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE events SET actor = 'tampered' WHERE event_id = 1")


if __name__ == "__main__":
    unittest.main()
