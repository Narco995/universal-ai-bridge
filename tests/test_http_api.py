import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from universal_ai_bridge.http_api import BridgeHTTPServer
from universal_ai_bridge.core import BridgeService


class BridgeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        service = BridgeService(Path(self.tmp.name) / "api.sqlite3")
        self.server = BridgeHTTPServer(("127.0.0.1", 0), service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.connection = HTTPConnection("127.0.0.1", self.port, timeout=3)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request_json(self, method, path, payload=None, token=None, spoof_actor=None):
        body = json.dumps(payload or {}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if spoof_actor:
            headers["X-Bridge-Actor"] = spoof_actor
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data

    def create_task(self, required_authors=("claude",)):
        status, task = self.request_json("POST", "/tasks", {
            "objective": "Test authenticated workflow",
            "acceptance_criteria": ["Enforce participant and owner permissions"],
            "mode": "independent",
            "required_authors": list(required_authors),
        })
        self.assertEqual(status, 201)
        return task, task["credentials"]

    def test_http_positions_are_sealed_and_author_is_derived_from_token(self):
        task, credentials = self.create_task(("claude", "gpt"))
        task_id = task["task_id"]
        claude_token = credentials["participant_tokens"]["claude"]
        gpt_token = credentials["participant_tokens"]["gpt"]
        owner_token = credentials["owner_token"]

        status, _ = self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"content": "Claude position"}, token=claude_token,
        )
        self.assertEqual(status, 201)

        # Caller-supplied author fields cannot override the authenticated identity.
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"author": "claude", "content": "Impersonation attempt"}, token=gpt_token,
        )
        self.assertEqual(status, 400)
        self.assertIn("derived from the bearer credential", response["message"])

        status, _ = self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"content": "GPT position"}, token=gpt_token,
        )
        self.assertEqual(status, 201)

        # Spoofing X-Bridge-Actor must not change the bearer identity.
        status, listing = self.request_json(
            "GET", f"/tasks/{task_id}/positions",
            token=gpt_token, spoof_actor="claude",
        )
        self.assertEqual(status, 200)
        claude_row = next(p for p in listing["positions"] if p["author"] == "claude")
        gpt_row = next(p for p in listing["positions"] if p["author"] == "gpt")
        self.assertNotIn("content", claude_row)
        self.assertEqual(gpt_row["content"], "GPT position")

        # The owner can administer the task but cannot read sealed participant positions.
        status, listing = self.request_json(
            "GET", f"/tasks/{task_id}/positions", token=owner_token,
        )
        self.assertEqual(status, 200)
        self.assertNotIn("content", next(p for p in listing["positions"] if p["author"] == "claude"))

        status, _ = self.request_json("POST", f"/tasks/{task_id}/reveal", token=owner_token)
        self.assertEqual(status, 200)
        status, listing = self.request_json(
            "GET", f"/tasks/{task_id}/positions", token=gpt_token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(next(p for p in listing["positions"] if p["author"] == "claude")["content"], "Claude position")

    def test_http_requires_valid_token_and_participant_cannot_reveal(self):
        task, credentials = self.create_task(("claude",))
        task_id = task["task_id"]
        status, response = self.request_json("GET", f"/tasks/{task_id}/positions")
        self.assertEqual(status, 401)
        self.assertEqual(response["error"], "Unauthorized")

        claude_token = credentials["participant_tokens"]["claude"]
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/reveal", token=claude_token,
        )
        self.assertEqual(status, 403)
        self.assertEqual(response["error"], "Forbidden")

    def test_http_owner_token_is_not_exposed_in_audit_export(self):
        task, credentials = self.create_task(("claude",))
        task_id = task["task_id"]
        status, exported = self.request_json(
            "GET", f"/tasks/{task_id}/export", token=credentials["owner_token"],
        )
        self.assertEqual(status, 200)
        serialized = json.dumps(exported)
        self.assertNotIn(credentials["owner_token"], serialized)
        self.assertNotIn(credentials["participant_tokens"]["claude"], serialized)

    def test_http_rejects_non_boolean_approval_flag(self):
        task, credentials = self.create_task(("claude",))
        task_id = task["task_id"]
        self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"content": "Proposal"}, token=credentials["participant_tokens"]["claude"],
        )
        self.request_json("POST", f"/tasks/{task_id}/reveal", token=credentials["owner_token"])
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/decisions",
            {"choice": "A", "rationale": "test", "requires_approval": "false"},
            token=credentials["owner_token"],
        )
        self.assertEqual(status, 400)
        self.assertIn("JSON boolean", response["message"])

    def test_http_high_impact_action_requires_exact_approval(self):
        task, credentials = self.create_task(("claude",))
        task_id = task["task_id"]
        owner_token = credentials["owner_token"]
        self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"content": "Proposal"}, token=credentials["participant_tokens"]["claude"],
        )
        self.request_json("POST", f"/tasks/{task_id}/reveal", token=owner_token)
        self.request_json(
            "POST", f"/tasks/{task_id}/decisions",
            {"choice": "A", "rationale": "Accepted", "requires_approval": False},
            token=owner_token,
        )
        request = {"action_name": "deploy", "target": "production", "scope": "release 1.0"}
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/actions/authorize", request, token=owner_token,
        )
        self.assertEqual(status, 423)
        self.assertEqual(response["error"], "ApprovalRequired")

        self.request_json(
            "POST", f"/tasks/{task_id}/approvals",
            {
                "action": "approve", "note": "Approved exact release",
                "action_name": "deploy", "target": "production", "scope": "release 1.0",
            },
            token=owner_token,
        )
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/actions/authorize", request, token=owner_token,
        )
        self.assertEqual(status, 200)
        self.assertTrue(response["authorized"])

    def test_http_decision_approval_gate_blocks_until_approved(self):
        task, credentials = self.create_task(("claude",))
        task_id = task["task_id"]
        owner_token = credentials["owner_token"]
        self.request_json(
            "POST", f"/tasks/{task_id}/positions",
            {"content": "Proposal"}, token=credentials["participant_tokens"]["claude"],
        )
        self.request_json("POST", f"/tasks/{task_id}/reveal", token=owner_token)
        self.request_json(
            "POST", f"/tasks/{task_id}/decisions",
            {"choice": "A", "rationale": "It is acceptable", "requires_approval": True},
            token=owner_token,
        )
        action_request = {
            "action_name": "deploy",
            "target": "production/api",
            "scope": "release version 1.2.3",
        }
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/actions/authorize", action_request, token=owner_token,
        )
        self.assertEqual(status, 423)
        self.assertEqual(response["error"], "ApprovalRequired")

        approval = {
            "action": "approve", "note": "Approved",
            "action_name": "deploy", "target": "production/api",
            "scope": "release version 1.2.3",
        }
        self.request_json(
            "POST", f"/tasks/{task_id}/approvals", approval, token=owner_token,
        )
        status, response = self.request_json(
            "POST", f"/tasks/{task_id}/actions/authorize", action_request, token=owner_token,
        )
        self.assertEqual(status, 200)
        self.assertTrue(response["authorized"])
        self.assertFalse(response["executed"])


if __name__ == "__main__":
    unittest.main()
