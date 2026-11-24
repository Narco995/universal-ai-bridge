import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from universal_ai_bridge.core import BridgeService
from universal_ai_bridge.http_api import BridgeHTTPServer


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

    def request_json(self, method, path, payload=None, actor="human"):
        body = json.dumps(payload or {}).encode("utf-8")
        self.connection.request(method, path, body=body, headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "X-Bridge-Actor": actor,
        })
        response = self.connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data

    def test_server_constructor_rejects_non_loopback_binding(self):
        with self.assertRaises(ValueError):
            BridgeHTTPServer(("0.0.0.0", 0), self.server.service)

    def test_http_positions_are_sealed_by_viewer_identity(self):
        status, task = self.request_json("POST", "/tasks", {
            "objective": "Test sealed positions",
            "acceptance_criteria": ["A cannot read B before reveal"],
            "mode": "independent",
            "required_authors": ["claude", "gpt"],
        })
        self.assertEqual(status, 201)
        task_id = task["task_id"]
        self.request_json("POST", f"/tasks/{task_id}/positions", {"author": "claude", "content": "Claude position"})
        self.request_json("POST", f"/tasks/{task_id}/positions", {"author": "gpt", "content": "GPT position"})
        status, listing = self.request_json("GET", f"/tasks/{task_id}/positions", actor="gpt")
        self.assertEqual(status, 200)
        claude_row = next(p for p in listing["positions"] if p["author"] == "claude")
        gpt_row = next(p for p in listing["positions"] if p["author"] == "gpt")
        self.assertNotIn("content", claude_row)
        self.assertEqual(gpt_row["content"], "GPT position")
        self.request_json("POST", f"/tasks/{task_id}/reveal")
        status, listing = self.request_json("GET", f"/tasks/{task_id}/positions", actor="gpt")
        self.assertEqual(status, 200)
        self.assertEqual(next(p for p in listing["positions"] if p["author"] == "claude")["content"], "Claude position")

    def test_http_rejects_non_boolean_approval_flag(self):
        _, task = self.request_json("POST", "/tasks", {
            "objective": "Validate booleans",
            "acceptance_criteria": ["Reject string truthiness"],
            "required_authors": ["claude"],
        })
        task_id = task["task_id"]
        self.request_json("POST", f"/tasks/{task_id}/positions", {"author": "claude", "content": "Proposal"})
        self.request_json("POST", f"/tasks/{task_id}/reveal")
        status, response = self.request_json("POST", f"/tasks/{task_id}/decisions", {
            "choice": "A", "rationale": "test", "requires_approval": "false"
        })
        self.assertEqual(status, 400)
        self.assertIn("JSON boolean", response["message"])

    def test_http_high_impact_action_requires_approval_even_when_decision_flag_is_false(self):
        _, task = self.request_json("POST", "/tasks", {
            "objective": "Protect high-impact actions",
            "acceptance_criteria": ["deploy cannot bypass approval"],
            "required_authors": ["claude"],
        })
        task_id = task["task_id"]
        self.request_json("POST", f"/tasks/{task_id}/positions", {"author": "claude", "content": "Proposal"})
        self.request_json("POST", f"/tasks/{task_id}/reveal")
        self.request_json("POST", f"/tasks/{task_id}/decisions", {
            "choice": "A", "rationale": "Accepted", "requires_approval": False
        })
        request = {"action_name": "deploy", "target": "production", "scope": "release 1.0"}
        status, response = self.request_json("POST", f"/tasks/{task_id}/actions/authorize", request)
        self.assertEqual(status, 423)
        self.assertEqual(response["error"], "ApprovalRequired")
        self.request_json("POST", f"/tasks/{task_id}/approvals", {
            "action": "approve", "note": "Approved exact release",
            "action_name": "deploy", "target": "production", "scope": "release 1.0",
        })
        status, response = self.request_json("POST", f"/tasks/{task_id}/actions/authorize", request)
        self.assertEqual(status, 200)
        self.assertTrue(response["authorized"])

    def test_http_approval_gate_returns_locked_until_approved(self):
        _, task = self.request_json("POST", "/tasks", {
            "objective": "Test approval",
            "acceptance_criteria": ["block before approval"],
            "required_authors": ["claude"],
        })
        task_id = task["task_id"]
        self.request_json("POST", f"/tasks/{task_id}/positions", {"author": "claude", "content": "Proposal"})
        self.request_json("POST", f"/tasks/{task_id}/reveal")
        self.request_json("POST", f"/tasks/{task_id}/decisions", {"choice": "A", "rationale": "It is acceptable", "requires_approval": True})
        action_request = {"action_name": "deploy", "target": "production/api", "scope": "release version 1.2.3"}
        status, response = self.request_json("POST", f"/tasks/{task_id}/actions/authorize", action_request)
        self.assertEqual(status, 423)
        self.assertEqual(response["error"], "ApprovalRequired")
        approval = {
            "action": "approve", "note": "Approved",
            "action_name": "deploy", "target": "production/api", "scope": "release version 1.2.3",
        }
        self.request_json("POST", f"/tasks/{task_id}/approvals", approval)
        status, response = self.request_json("POST", f"/tasks/{task_id}/actions/authorize", action_request)
        self.assertEqual(status, 200)
        self.assertTrue(response["authorized"])
        self.assertFalse(response["executed"])


if __name__ == "__main__":
    unittest.main()
