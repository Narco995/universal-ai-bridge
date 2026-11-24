import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_ai_bridge import ApprovalRequired, BridgeService, Conflict, Forbidden


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

    def test_sealed_positions_are_hidden_until_reveal(self):
        claude = self.service.submit_position(self.task_id, "claude", "Use append-only SQLite events")
        gpt = self.service.submit_position(self.task_id, "gpt", "Use mutable JSON snapshots")
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
        self.service.record_decision(self.task_id, "A", "A meets the criteria", [p1["position_id"]], [], True)
        action = "modify_shared_infrastructure"
        target = "repository/main"
        scope = "change collaboration workflow"
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, action, target=target, scope=scope)
        self.service.record_approval(
            self.task_id, "approve", "Reviewed and approved",
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
                action_name=action, target=target, scope=scope,
            )
        self.service.record_approval(
            self.task_id, "approve", "Human principal reviewed scope and evidence", actor="human",
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

    def test_allowlisted_low_risk_action_does_not_need_scoped_approval(self):
        self.service.submit_position(self.task_id, "claude", "Option A")
        self.service.submit_position(self.task_id, "gpt", "Option B")
        self.service.reveal(self.task_id)
        self.service.record_decision(self.task_id, "A", "Routine decision")
        result = self.service.authorize_action(
            self.task_id, "export", target=self.task_id, scope="read-only timeline export"
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
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}):
                service = BridgeService("~/bridge-test.sqlite3")
                self.assertEqual(service.database, str(Path(home) / "bridge-test.sqlite3"))

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
        with sqlite3.connect(self.service.database) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE events SET actor = 'tampered' WHERE event_id = 1")


if __name__ == "__main__":
    unittest.main()
