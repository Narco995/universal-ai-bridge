# MCP stdio transport v0.1

## Purpose

The Bridge exposes its shared `BridgeService` through the official MCP Python SDK. MCP tool handlers call the same core as the CLI and HTTP API; workflow logic is not duplicated.

The initial MCP transport is **stdio only**. Each MCP host launches one Bridge process. Create one process per task-scoped principal, point every process at the same SQLite database, and supply only that principal's token.

The process identity is resolved at startup from the bearer token and task-scoped principal record. The MCP tool catalog is filtered by role:

- A participant process receives submit and read tools for its own task.
- The owner process receives reveal, decision, action-authorization, artifact-attachment and integrity tools. Artifact verification remains a human-only operation through the trusted CLI or owner HTTP path.
- An unconfigured process exposes health only.

The caller cannot pass an author label or choose a different task. Tool calls are bound to the task associated with the process token.

## Install

Requires Python 3.10 or newer. Install the project and its official MCP SDK dependency:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The package uses `mcp>=2.3,<3`, the official Python SDK v2 line. The executable is `uab-mcp`.

## Create a task and issue credentials

Task creation and credential issuance are deliberately kept outside model-callable MCP tools. Use the trusted CLI or loopback HTTP API:

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

The command prints one-time credentials. Store the owner token securely and distribute each participant token only to its intended MCP host. Do not place tokens in Git or shared model prompts.

For an optional participant not listed at creation, the owner may issue a token while collection remains open:

```bash
uab --db /absolute/path/bridge.sqlite3 participant issue TASK_ID --name grok
```

Manual/early collection close and human approvals also remain in the trusted CLI or loopback HTTP API. This prevents an agent from issuing credentials to itself, closing a collection prematurely, or approving its own consequential action.

## Configure one process per principal

Each MCP process receives the same absolute database path and exactly one task-scoped token. Example generic host configuration:

```json
{
  "mcpServers": {
    "universal-ai-bridge-claude": {
      "command": "/absolute/path/to/universal-ai-bridge/.venv/bin/uab-mcp",
      "args": ["--database", "/absolute/path/bridge.sqlite3"],
      "env": {
        "UAB_TOKEN": "<claude-participant-token>",
        "UAB_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

Create separate entries for GPT, Grok and the human owner, replacing the server name and token. Use the owner token only in the founder's private MCP host configuration. Never share it with participant models.

The host launches the server as a subprocess. MCP protocol messages use stdin/stdout; diagnostics go to stderr. Do not wrap the command in a script that prints banners or other text to stdout. Tokens are read at process startup; restart the host after changing credentials.

## Tools and permissions

| Tool | Participant | Owner | Purpose |
|---|---:|---:|---|
| `bridge_health` | Yes | Yes | Health and truthful provider-connection status |
| `task_get` | Yes | Yes | Read task metadata for the bound task |
| `positions_list` | Own view | Sealed view | List positions visible to this principal |
| `timeline_export` | Filtered | Filtered | Export the principal's permitted timeline |
| `position_submit` | Yes | No | Submit under identity derived from participant token |
| `positions_reveal` | No | Yes | Reveal positions once collection is ready |
| `decision_record` | No | Yes | Record a decision and link supporting/dissenting positions |
| `action_authorize` | No | Yes | Check an exact, unexpired approval; does not execute |
| `artifact_attach` | No | Yes | Attach a pending pointer to implementation evidence |
| `event_chain_verify` | No | Yes | Verify event hashes and reconstructed state |

The following are intentionally **not exposed as model-callable MCP tools**: task creation, participant credential issuance, manual collection close, approval recording, and artifact verification. Use the trusted CLI or owner HTTP API for these operations.

A participant can read its own sealed position before reveal. The owner can administer the task but does not see participant bodies until reveal. After reveal, all task principals can read all positions. Open mode is intentionally visible without a reveal step.

## Approval semantics

A decision marked `requires_approval=true` needs a separate `decision_acceptance` approval bound to its task ID and decision ID. A consequential action then needs its own exact approval matching action name, target and scope. Both approvals must remain unexpired. Approval recording is performed by the human through CLI/HTTP, not by an MCP tool.

An action approval is one-time: the Bridge consumes it atomically inside the same SQLite write transaction as the authorization record. Replays and concurrent reuse are rejected, and an `approval_consumed` event is linked to the `action_authorized` event. The separate decision-acceptance approval remains a decision gate and is not consumed by action authorization.

The MCP `action_authorize` tool consumes the one-time action approval and records a permission check only. It does not execute a side effect, so do not call it as a preflight and expect to reuse the approval later. A future executor should combine capability validation, approval consumption, and immediate dispatch in one governed tool invocation. The MCP `artifact_attach` tool records a pending pointer but cannot mark work implemented; the human owner must separately inspect and verify the evidence.

## Security limits

- Without `UAB_TOKEN`, only `bridge_health` is exposed. An invalid token fails server startup.
- Each process is bound to one task-scoped principal. A token cannot be reused against a different task.
- The token label is a participant slot, not proof of a verified Claude/GPT/Grok account.
- All position submissions are marked manual until provider adapters are implemented.
- This is local stdio, not remote deployment. There is no Streamable HTTP MCP endpoint, OAuth, TLS, token rotation/revocation or signed approval credential.
- Anyone with direct SQLite file access or local administrator access can bypass application-level filtering.
- The Bridge does not invoke model-provider APIs. MCP hosts run their own models; this server supplies shared tools and durable state.

Do not use this version as a production security boundary or to authorize real-world side effects.

## Verification

Automated tests cover role-filtered tool discovery, multiple participant processes sharing state, sealed-position visibility before reveal, owner-only operations, blocked authorization without human approval, artifact attachment without model-side completion, human-only artifact verification, and a real stdio subprocess handshake.
