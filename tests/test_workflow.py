import tempfile
import unittest
from pathlib import Path

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
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, "modify_shared_infrastructure")
        self.service.record_approval(self.task_id, "approve", "Reviewed and approved")
        self.service.authorize_action(self.task_id, "modify_shared_infrastructure")
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
        with self.assertRaises(ApprovalRequired):
            self.service.authorize_action(self.task_id, "change_security_policy")
        with self.assertRaises(ApprovalRequired):
            self.service.attach_artifact(self.task_id, "commit", "https://example.invalid/commit/blocked")
        with self.assertRaises(Forbidden):
            self.service.record_approval(self.task_id, "approve", "not the principal", actor="gpt")
        self.service.record_approval(self.task_id, "approve", "Human principal reviewed scope and evidence", actor="human")
        result = self.service.authorize_action(self.task_id, "change_security_policy")
        self.assertTrue(result["authorized"])
        self.assertFalse(result["executed"])

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
