# MCP stdio Setup v0.1

The Universal AI Bridge exposes MCP tools through the official Python MCP SDK. The MCP server is a thin adapter over the same \`BridgeService\` used by the CLI and HTTP API. It uses stdio transport only.

## Requirements

- Python 3.10 or newer.
- A local Bridge SQLite database.
- A task-scoped owner or participant token.
- A local MCP host that supports stdio servers.

Install the project:

\`\`\`bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
uab-mcp --help
\`\`\`

The MCP dependency is the official \`mcp\` Python SDK (v2.x). The SDK's PyPI metadata specifies Python 3.10+ and documents \`MCPServer\`, stdio, and \`Client\`. The Bridge currently uses \`MCPServer\` over stdio.

## Create a task and issue credentials

Create a task through the trusted CLI or loopback HTTP API, not through an AI-callable MCP tool:

\`\`\`bash
uab --db /absolute/path/bridge.sqlite3 task create \\
  --objective "Choose a persistence design" \\
  --criteria "Preserve dissent" \\
  --mode independent \\
  --required-author claude \\
  --required-author gpt
\`\`\`

The result includes a one-time owner token and one-time participant tokens. Save them securely and distribute only the relevant participant token to each model's MCP host configuration. Do not commit tokens to the repository or paste the owner token into model prompts.

For an open task with no predefined authors, issue participant credentials while collection is open:

\`\`\`bash
uab --db /absolute/path/bridge.sqlite3 participant issue TASK_ID --name grok
\`\`\`

The raw token is returned once; only its SHA-256 hash is stored.

## Configure one process per principal

Each MCP process receives the same absolute database path and exactly one task-scoped token. Do not share the owner token with participant processes.

Example generic stdio MCP host configuration:

\`\`\`json
{
  "mcpServers": {
    "uab-claude": {
      "command": "/absolute/path/to/project/.venv/bin/uab-mcp",
      "args": ["--database", "/absolute/path/bridge.sqlite3"],
      "env": {
        "UAB_TOKEN": "<claude-participant-token>",
        "UAB_LOG_LEVEL": "WARNING"
      }
    },
    "uab-gpt": {
      "command": "/absolute/path/to/project/.venv/bin/uab-mcp",
      "args": ["--database", "/absolute/path/bridge.sqlite3"],
      "env": {
        "UAB_TOKEN": "<gpt-participant-token>",
        "UAB_LOG_LEVEL": "WARNING"
      }
    },
    "uab-owner": {
      "command": "/absolute/path/to/project/.venv/bin/uab-mcp",
      "args": ["--database", "/absolute/path/bridge.sqlite3"],
      "env": {
        "UAB_TOKEN": "<owner-token>",
        "UAB_LOG_LEVEL": "WARNING"
      }
    }
  }
}
\`\`\`

Adapt the host's configuration location and JSON shape to its own documentation. Use absolute executable and database paths. The host launches the server process; the server speaks MCP over stdin/stdout. Logs are sent to stderr so they do not corrupt the protocol stream.

## Tool permissions

Participant processes can:
- Read task metadata.
- Submit a position under the identity bound to their token.
- Read their own sealed position.
- Read all positions after reveal.
- Export a visibility-filtered timeline.

The owner process can:
- Read task metadata and the event/projection integrity result.
- List positions without seeing sealed participant bodies before reveal.
- Reveal positions once the task is ready.
- Record a decision.
- Request action authorization (which remains blocked until the human approval is present).
- Attach an artifact pointer, subject to the decision-acceptance gate.

The following operations are intentionally **not exposed as model-callable MCP tools**:
- Task creation and participant credential issuance.
- Early/manual collection close.
- Recording human approvals.

Use the trusted CLI or owner HTTP API for those operations. This prevents an agent connected to the owner MCP process from issuing credentials to itself, closing a collection early, or approving its own consequential action. A human approval is not an MCP model tool.

## Important behavior

- One MCP process is bound to one task-scoped token. A participant cannot use its token against another task.
- The MCP server does not infer provider identity. The token label identifies the participant slot, not a verified Claude/GPT/Grok account.
- All position submissions are marked manual until provider adapters are implemented.
- The owner MCP process can reveal positions only after the required submissions make the task ready. If a required participant is missing, the human must close the collection through CLI/HTTP.
- Every action-authorization request requires a separate, exact, unexpired human approval. A decision marked \`requires_approval=true\` also requires a separate \`decision_acceptance\` approval before artifact attachment.
- The MCP authorization tool records a check only; it never executes a real side effect.
- Without \`UAB_TOKEN\`, the MCP process exposes health only.

## Security limitations

This is local stdio integration, not a remote deployment. Tokens are bearer secrets. Protect the MCP host configuration file and its permissions. There is no TLS, token rotation/revocation workflow, provider identity binding, or signed approval credential. A person with direct database-file access can bypass application-level filtering. Do not use this version to authorize production or other real-world side effects.
