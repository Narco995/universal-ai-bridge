import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from universal_ai_bridge.core import BridgeService
from universal_ai_bridge.mcp_server import build_mcp_server


class BridgeMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_participant_processes_share_state_without_reading_sealed_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "bridge.sqlite3"
            service = BridgeService(database)
            task = service.create_task(
                "Verify independent MCP clients",
                ["Keep independent positions sealed", "Preserve both contributions"],
                mode="independent",
                required_authors=["claude", "gpt"],
            )
            task_id = task["task_id"]
            credentials = task["credentials"]

            claude_server = build_mcp_server(database, credentials["participant_tokens"]["claude"])
            gpt_server = build_mcp_server(database, credentials["participant_tokens"]["gpt"])
            owner_server = build_mcp_server(database, credentials["owner_token"])

            async with (
                Client(claude_server) as claude,
                Client(gpt_server) as gpt,
                Client(owner_server) as owner,
            ):
                listing = await claude.list_tools()
                names = {tool.name for tool in listing.tools}
                self.assertIn("position_submit", names)
                self.assertIn("positions_reveal", names)
                self.assertIn("timeline_export", names)

                claude_submit = await claude.call_tool(
                    "position_submit",
                    {"task_id": task_id, "content": "Claude's independent architecture proposal"},
                )
                self.assertFalse(claude_submit.is_error)
                self.assertEqual(claude_submit.structured_content["author"], "claude")

                gpt_submit = await gpt.call_tool(
                    "position_submit",
                    {"task_id": task_id, "content": "GPT's independent implementation proposal"},
                )
                self.assertFalse(gpt_submit.is_error)
                self.assertEqual(gpt_submit.structured_content["author"], "gpt")

                gpt_view = await gpt.call_tool("positions_list", {"task_id": task_id})
                self.assertFalse(gpt_view.is_error)
                gpt_positions = gpt_view.structured_content["positions"]
                claude_row = next(position for position in gpt_positions if position["author"] == "claude")
                gpt_row = next(position for position in gpt_positions if position["author"] == "gpt")
                self.assertNotIn("content", claude_row)
                self.assertEqual(gpt_row["content"], "GPT's independent implementation proposal")

                owner_view = await owner.call_tool("positions_list", {"task_id": task_id})
                self.assertFalse(owner_view.is_error)
                self.assertTrue(
                    all("content" not in position for position in owner_view.structured_content["positions"])
                )

                denied_reveal = await gpt.call_tool("positions_reveal", {"task_id": task_id})
                self.assertTrue(denied_reveal.is_error)

                reveal = await owner.call_tool("positions_reveal", {"task_id": task_id})
                self.assertFalse(reveal.is_error)

                after_reveal = await claude.call_tool("positions_list", {"task_id": task_id})
                self.assertFalse(after_reveal.is_error)
                visible = {p["author"]: p.get("content") for p in after_reveal.structured_content["positions"]}
                self.assertEqual(visible["claude"], "Claude's independent architecture proposal")
                self.assertEqual(visible["gpt"], "GPT's independent implementation proposal")

                integrity = await owner.call_tool("event_chain_verify", {"task_id": task_id})
                self.assertFalse(integrity.is_error)
                self.assertTrue(integrity.structured_content["valid"])

    async def test_stdio_entrypoint_uses_its_process_token_and_shared_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "bridge.sqlite3"
            service = BridgeService(database)
            task = service.create_task(
                "Verify real stdio transport",
                ["The stdio process uses its own identity"],
                required_authors=["claude"],
            )
            token = task["credentials"]["participant_tokens"]["claude"]
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "universal_ai_bridge.mcp_server"],
                env={
                    "UAB_DATABASE": str(database),
                    "UAB_TOKEN": token,
                    "UAB_LOG_LEVEL": "ERROR",
                },
            )
            async with Client(stdio_client(parameters)) as client:
                result = await client.call_tool("task_get", {"task_id": task["task_id"]})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["task_id"], task["task_id"])

                submitted = await client.call_tool(
                    "position_submit",
                    {"task_id": task["task_id"], "content": "Position delivered through stdio"},
                )
                self.assertFalse(submitted.is_error)
                self.assertEqual(submitted.structured_content["author"], "claude")

            self.assertEqual(
                service.list_positions(task["task_id"], viewer="claude")[0]["content"],
                "Position delivered through stdio",
            )


if __name__ == "__main__":
    unittest.main()
