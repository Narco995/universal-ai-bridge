# MCP stdio transport v0

## What it provides

The Bridge exposes the shared `BridgeService` through the official MCP Python SDK. MCP tool handlers call the same core used by the CLI and HTTP API; no workflow logic is duplicated.

The initial MCP transport is **stdio**. Each MCP host launches one Bridge process. Start a separate process for each participant, give each process its own task-scoped bearer token, and point all processes at the same SQLite database.

This creates a real local collaboration boundary:

- Claude's process authenticates as the `claude` participant.
- GPT's process authenticates as the `gpt` participant.
- Grok's process authenticates as the `grok` participant.
- The founder's private process authenticates as the `human` owner. The MCP owner process can administer the workflow, but cannot create human approvals.

The identity is fixed by the process environment; the model cannot pass an `author` argument to impersonate another participant.

## Install

The project depends on the official MCP Python SDK 2.x:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The `mcp` dependency is constrained to `>=2.3,<3` so the project uses the stable v2 API without silently crossing a future major version.

## Bootstrap a task

Run the CLI to create a task:

```bash
uab --db /absolute/path/bridge.sqlite3 task create \
  --objective "Design the next Bridge milestone" \
  --criteria "Preserve independent positions" \
  --criteria "Keep rejected objections auditable" \
  --mode independent \
  --required-author claude \
  --required-author gpt \
  --required-author grok
```

The command prints one-time credentials. Store the owner token securely and distribute each participant token only to its intended MCP host. Do not place tokens in Git, task descriptions, or shared chat transcripts.

Task creation is intentionally performed through the trusted CLI or loopback HTTP API, not through an MCP tool. A process without `UAB_TOKEN` exposes only `bridge_health`. This keeps one-time owner and participant credentials out of model-visible MCP tool results.

For an optional participant not included at task creation, the human owner may run `uab participant issue TASK_ID --name grok` or use the owner-only HTTP route while collection remains open. This issues a token but does not make the new participant a required author for automatic collection completion.

## Configure each MCP host

Use an absolute path to the installed `uab-mcp` executable and the same absolute SQLite path in every process. The token value is illustrative; use the actual one-time credential from task creation.

```json
{
  "mcpServers": {
    "universal-ai-bridge-claude": {
      "command": "/absolute/path/to/universal-ai-bridge/.venv/bin/uab-mcp",
      "env": {
        "UAB_DATABASE": "/absolute/path/bridge.sqlite3",
        "UAB_TOKEN": "<claude-participant-token>"
      }
    }
  }
}
```

Create separate entries for GPT and Grok, replacing the server name and token. Configure the founder's private Bridge process with `credentials.owner_token`. Never share the owner token with a participant model; it grants reveal, decision, action-authorization, and artifact-administration privileges. Human approvals remain outside the MCP tool surface.

The SDK's stdio client launches this command as a subprocess. The server writes protocol messages to stdout; diagnostics are sent to stderr. Do not wrap the command in scripts that print banners or other text to stdout.

Environment variables are read at process startup. Restart the MCP host after rotating or changing a token.

## Tools

| Tool | Access | Purpose |
|---|---|---|
| `bridge_health` | Public | Report health and truthful manual/not-connected status |
| `task_get` | Owner or participant | Read task metadata |
| `position_submit` | Participant | Submit a position as the authenticated author |
| `positions_list` | Owner or participant | Read own sealed position; all positions after reveal |
| `positions_reveal` | Owner | Reveal positions only when collection is ready |
| `decision_record` | Owner | Record the choice and considered objections |
| `action_authorize` | Owner | Check exact action/target/scope approval; does not execute |
| `artifact_attach` | Owner | Attach an implementation artifact pointer, subject to decision approval |
| `timeline_export` | Owner or participant | Export the view permitted to this identity |
| `event_chain_verify` | Owner | Verify the global event chain, projections, and reconstructed state |

The following operations are intentionally **not MCP tools**: task creation, participant credential issuance, early/manual collection close, and recording human approvals. Use the trusted CLI or owner HTTP API for these operations. This prevents an agent connected to an owner MCP process from minting credentials, forcing an early reveal, or approving its own consequential action.

A decision marked as requiring approval needs a separate `decision_acceptance` approval bound to its task ID and decision ID. A consequential action then needs its own matching action-name, target, and scope approval. Both approvals must be unexpired. The MCP server cannot create either approval; the human uses the trusted CLI or HTTP API. The Bridge does not execute side effects in this version.

## Local configuration and limitations

- `UAB_DATABASE` selects the shared SQLite database. Every participant process must point to the same file.
- `UAB_TOKEN` selects the task-scoped identity for that process. Without it, only health and task bootstrap are available.
- Tokens are hashed in the database; the raw token is returned once at issuance.
- The process identity is not an identity-provider assertion. A local machine administrator or someone with direct SQLite access can bypass application-level access controls.
- The MCP server is stdio-only in this milestone. There is no remote Streamable HTTP MCP endpoint, OAuth, TLS, or external multi-user deployment.
- The Bridge does not call Claude, GPT, or Grok provider APIs. MCP hosts run their own models; this server provides shared tools and durable state. A tool invocation does not prove that an external model is connected unless the host itself establishes that connection.
- A single MCP process has one task-scoped token. Use one process/configuration per task and participant for this version.

## Verification

The MCP tests cover:

1. MCP tool discovery and structured tool results through an in-memory SDK client.
2. Two participant processes sharing a database while sealed positions remain private.
3. Owner-only reveal and post-reveal visibility.
4. Participant inability to call owner-only tools.
5. The owner MCP process cannot issue credentials, close collection early, or record human approvals.
6. A real stdio subprocess handshake and tool call using its own task-scoped token.

The project uses the official Python SDK's `MCPServer` and stdio transport. See the upstream [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) for protocol and transport details.
