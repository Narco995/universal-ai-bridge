from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from .core import BridgeService, Forbidden, Unauthorized


def build_mcp_server(
    database: str | Path | None = None,
    token: str | None = None,
) -> MCPServer:
    """Build an MCP server whose process identity is fixed by its task-scoped token.

    Run one process per participant, pointing each process at the same SQLite file
    and giving it only that participant's UAB_TOKEN. Create tasks, issue credentials,
    close incomplete collections, and record human approvals through the trusted CLI
    or loopback HTTP API. Those credential and approval operations are deliberately
    not exposed as model-callable MCP tools. Without a token, only health is available.
    """
    db_path = database or os.environ.get("UAB_DATABASE", "bridge.sqlite3")
    process_token = token if token is not None else os.environ.get("UAB_TOKEN")
    service = BridgeService(db_path)
    server = MCPServer(
        "Universal AI Bridge",
        instructions=(
            "Coordinate evidence-based collaboration through the shared Bridge core. "
            "Positions are manually submitted unless a provider adapter explicitly says otherwise. "
            "Never claim a model is connected or that a side effect executed unless the tool result proves it. "
            "Participant identity is derived from this MCP process's task-scoped credential. "
            "Task creation, participant credential issuance, early collection close, and human approval "
            "are deliberately kept outside the model-callable MCP surface; use the trusted CLI or owner HTTP API."
        ),
    )

    def principal_for(task_id: str) -> dict[str, str]:
        if not process_token:
            raise Unauthorized(
                "this MCP process has no UAB_TOKEN; create a task through the trusted CLI or HTTP API, then restart with its owner or participant token"
            )
        return service.authenticate_principal(task_id, process_token)

    def owner_for(task_id: str) -> dict[str, str]:
        principal = principal_for(task_id)
        if principal["role"] != "owner":
            raise Forbidden("this tool requires the task owner credential")
        return principal

    @server.tool()
    def bridge_health() -> dict[str, str]:
        """Return Bridge health and truthful provider-connection status."""
        return {
            "status": "ok",
            "agent_connections": "not_connected",
            "submission_mode": "manual",
            "transport": "mcp_stdio",
        }

    @server.tool()
    def task_get(task_id: str) -> dict[str, Any]:
        """Read task metadata using this process's task-scoped credential."""
        principal_for(task_id)
        return service.get_task(task_id)

    @server.tool()
    def position_submit(task_id: str, content: str) -> dict[str, Any]:
        """Submit this process's independent position; author is derived from its token."""
        principal = principal_for(task_id)
        if principal["role"] != "participant":
            raise Forbidden("only a participant credential may submit a position")
        return service.submit_position(task_id, principal["name"], content, actor=principal["name"])

    @server.tool()
    def positions_list(task_id: str) -> dict[str, Any]:
        """List positions visible to this principal; sealed positions remain private until reveal."""
        principal = principal_for(task_id)
        viewer = principal["name"] if principal["role"] == "participant" else "__task_owner__"
        return {"positions": service.list_positions(task_id, viewer)}

    @server.tool()
    def positions_reveal(task_id: str) -> dict[str, Any]:
        """Reveal all sealed positions once the collection is ready; owner credential required."""
        principal = owner_for(task_id)
        return service.reveal(task_id, actor=principal["name"])

    @server.tool()
    def decision_record(
        task_id: str,
        choice: str,
        rationale: str,
        supporting_position_ids: list[str] | None = None,
        considered_not_chosen_position_ids: list[str] | None = None,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        """Record a decision while preserving supporting and dissenting position references."""
        principal = owner_for(task_id)
        return service.record_decision(
            task_id,
            choice,
            rationale,
            supporting_position_ids,
            considered_not_chosen_position_ids,
            requires_approval,
            actor=principal["name"],
        )

    @server.tool()
    def action_authorize(
        task_id: str,
        action_name: str,
        target: str,
        scope: str,
    ) -> dict[str, Any]:
        """Check an exact action approval; this records authorization and does not execute the action."""
        principal = owner_for(task_id)
        return service.authorize_action(
            task_id,
            action_name,
            actor=principal["name"],
            target=target,
            scope=scope,
        )

    @server.tool()
    def artifact_attach(
        task_id: str,
        kind: str,
        uri: str,
        sha256: str | None = None,
    ) -> dict[str, Any]:
        """Attach a pointer to an implementation artifact; this does not execute or verify it."""
        principal = owner_for(task_id)
        return service.attach_artifact(
            task_id, kind, uri, sha256, actor=principal["name"]
        )

    @server.tool()
    def timeline_export(task_id: str) -> dict[str, Any]:
        """Export the reproducible task timeline with visibility filtered for this principal."""
        principal = principal_for(task_id)
        viewer = principal["name"] if principal["role"] == "participant" else "__task_owner__"
        return service.export_timeline(task_id, viewer=viewer)

    @server.tool()
    def event_chain_verify(task_id: str) -> dict[str, Any]:
        """Verify the database event chain and reconstructed state; owner credential required."""
        owner_for(task_id)
        return service.verify_event_chain()

    return server


def main() -> None:
    """Run the MCP server over stdio for a local MCP host."""
    parser = argparse.ArgumentParser(description="Universal AI Bridge MCP stdio server")
    parser.add_argument(
        "--database",
        default=os.environ.get("UAB_DATABASE", "bridge.sqlite3"),
        help="shared SQLite database path (default: UAB_DATABASE or ./bridge.sqlite3)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("UAB_LOG_LEVEL", "WARNING"), stream=sys.stderr)
    token = os.environ.get("UAB_TOKEN")
    server = build_mcp_server(args.database, token)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
