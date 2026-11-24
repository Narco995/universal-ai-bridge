from __future__ import annotations

import argparse
import logging
import os
import sys
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .core import BridgeError, BridgeService, Forbidden


def _tool_error_boundary(function):
    """Return expected Bridge/policy failures to the model as readable MCP tool errors."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (BridgeError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    return wrapped


def build_mcp_server(
    database: str | Path | None = None,
    token: str | None = None,
) -> MCPServer:
    """Build a role-filtered MCP server bound to one task-scoped principal.

    Each participant or owner runs a separate process, points it at the shared
    SQLite database, and provides only its own UAB_TOKEN. Task creation,
    participant issuance, early collection close, and human approval remain
    available through the trusted CLI/HTTP path, not model-callable MCP tools.
    Without a token, this process exposes health only.
    """
    db_path = database or os.environ.get("UAB_DATABASE", "bridge.sqlite3")
    process_token = token if token is not None else os.environ.get("UAB_TOKEN")
    service = BridgeService(db_path)
    identity = service.authenticate_principal_for_token(process_token) if process_token else None

    server = MCPServer(
        "Universal AI Bridge",
        instructions=(
            "Coordinate evidence-based collaboration through the shared Bridge core. "
            "This MCP process is bound to one task-scoped principal and exposes only that role's tools. "
            "Positions are marked manual unless a provider adapter explicitly proves otherwise. "
            "Never claim an external model is connected or a side effect executed unless a tool result proves it. "
            "Task creation, participant credential issuance, early collection close, and human approval "
            "are deliberately kept outside the model-callable MCP surface."
        ),
    )

    @server.tool()
    @_tool_error_boundary
    def bridge_health() -> dict[str, str]:
        """Return Bridge health and truthful provider-connection status."""
        return {
            "status": "ok",
            "agent_connections": "not_connected",
            "submission_mode": "manual",
            "transport": "mcp_stdio",
            "principal_role": identity["role"] if identity else "unconfigured",
        }

    if identity is None:
        return server

    def principal_for(task_id: str) -> dict[str, str]:
        if task_id != identity["task_id"]:
            raise Forbidden("this MCP process is bound to a different task")
        # Recheck the bearer token on every call so deletion or rotation takes effect.
        return service.authenticate_principal(task_id, process_token)

    def owner_for(task_id: str) -> dict[str, str]:
        principal = principal_for(task_id)
        if principal["role"] != "owner":
            raise Forbidden("this tool requires the task owner credential")
        return principal

    @server.tool()

    @_tool_error_boundary
    def task_get(task_id: str) -> dict[str, Any]:
        """Read metadata for the task bound to this MCP process."""
        principal_for(task_id)
        return service.get_task(task_id)

    @server.tool()

    @_tool_error_boundary
    def positions_list(task_id: str) -> dict[str, Any]:
        """List positions visible to this principal; sealed positions remain private until reveal."""
        principal = principal_for(task_id)
        viewer = principal["name"] if principal["role"] == "participant" else "__task_owner__"
        return {"positions": service.list_positions(task_id, viewer)}

    @server.tool()

    @_tool_error_boundary
    def timeline_export(task_id: str) -> dict[str, Any]:
        """Export the reproducible task timeline filtered for this principal."""
        principal = principal_for(task_id)
        viewer = principal["name"] if principal["role"] == "participant" else "__task_owner__"
        return service.export_timeline(task_id, viewer=viewer)

    if identity["role"] == "participant":
        @server.tool()
        @_tool_error_boundary
        def position_submit(task_id: str, content: str) -> dict[str, Any]:
            """Submit this participant's position; author is derived from this process's token."""
            principal = principal_for(task_id)
            return service.submit_position(
                task_id, principal["name"], content, actor=principal["name"]
            )
    else:
        @server.tool()
        @_tool_error_boundary
        def positions_reveal(task_id: str) -> dict[str, Any]:
            """Reveal positions once the collection is ready; owner credential required."""
            principal = owner_for(task_id)
            return service.reveal(task_id, actor=principal["name"])

        @server.tool()

        @_tool_error_boundary
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

        @_tool_error_boundary
        def action_authorize(
            task_id: str,
            action_name: str,
            target: str,
            scope: str,
        ) -> dict[str, Any]:
            """Check an exact human approval; this records authorization and does not execute the action."""
            principal = owner_for(task_id)
            return service.authorize_action(
                task_id,
                action_name,
                actor=principal["name"],
                target=target,
                scope=scope,
            )

        @server.tool()

        @_tool_error_boundary
        def artifact_attach(
            task_id: str,
            kind: str,
            uri: str,
            sha256: str | None = None,
        ) -> dict[str, Any]:
            """Attach an implementation artifact pointer; this does not execute or verify it."""
            principal = owner_for(task_id)
            return service.attach_artifact(
                task_id, kind, uri, sha256, actor=principal["name"]
            )

        @server.tool()

        @_tool_error_boundary
        def event_chain_verify(task_id: str) -> dict[str, Any]:
            """Verify the event chain and reconstructed state; owner credential required."""
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
