# Universal AI Bridge

A provider-neutral collaboration system for Claude, GPT, Grok, and compatible intelligence systems. MCP is the intended primary interface; CLI and HTTP are thin adapters over one shared application core.

## Current status

The feature branch contains a **minimal collaboration workflow v0.1 hardening pass**: a Python standard-library service, SQLite event store, CLI, loopback-only HTTP API, task-scoped participant credentials, scoped human approvals, event replay checks, and automated tests.

This is not yet a live multi-agent platform. There are no Claude, GPT, or Grok provider connections; participant positions are still manually relayed by the human operator. MCP, tool execution, remote deployment, and production hardening remain future work.

## Alliance principles

- Participants are independent intellectual peers; roles and leadership are task-specific.
- Any participant may propose, research, implement, test, or challenge a decision.
- Important dissent and rejected proposals remain linked to the decision record.
- Independent submissions are sealed until reveal; independent analysis still requires separate sessions and no cross-sharing before submission.
- The human founder remains the final acceptance and approval authority.
- Evidence, tests, and working artifacts—not model consensus—determine technical acceptance.

## Run locally

Requires Python 3.10 or newer. No third-party runtime dependencies are required.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

The CLI is a trusted local-owner interface. It prints task credentials when a task is created; protect that output. CLI author labels are operator-supplied because this path is intended for a single trusted administrator, not separate remote participants.

Example:

```bash
uab --db ./bridge.sqlite3 task create \
  --objective "Choose a persistence design" \
  --criteria "Preserve dissent" \
  --criteria "Block unapproved consequential actions" \
  --mode independent \
  --required-author claude \
  --required-author gpt

uab --db ./bridge.sqlite3 position submit TASK_ID --author claude --content "Append-only SQLite events"
uab --db ./bridge.sqlite3 position submit TASK_ID --author gpt --content "Mutable JSON snapshots"
uab --db ./bridge.sqlite3 task reveal TASK_ID

uab --db ./bridge.sqlite3 decision record TASK_ID \
  --choice "Append-only SQLite events" \
  --rationale "Replayable history is required" \
  --supporting POSITION_ID \
  --considered-not-chosen OTHER_POSITION_ID \
  --requires-approval

# Use the decision_id printed by the decision command:
uab --db ./bridge.sqlite3 approval TASK_ID --action approve \
  --action-name "decision_acceptance" \
  --target "TASK_ID" --scope "DECISION_ID" \
  --note "Human accepted the recorded decision"

# Separately approve the exact side effect:
uab --db ./bridge.sqlite3 approval TASK_ID --action approve \
  --action-name "modify_shared_infrastructure" \
  --target "repository/main" \
  --scope "change collaboration workflow" \
  --note "Approved this exact change"
uab --db ./bridge.sqlite3 action TASK_ID --name "modify_shared_infrastructure" \
  --target "repository/main" --scope "change collaboration workflow"
uab --db ./bridge.sqlite3 export TASK_ID --format markdown --output task-TASK_ID.md
uab --db ./bridge.sqlite3 verify events
```

A collection becomes ready automatically when every required author has submitted. The owner may also explicitly close a non-empty collection before revealing it.

## HTTP API and identity

Start the local API:

```bash
uab --db ./bridge.sqlite3 serve --host 127.0.0.1 --port 8000
```

Create a task with `POST /tasks`. The response includes one-time credentials:

- `credentials.owner_token`: owner-only operations such as reveal, decisions, approvals, and artifact attachment.
- `credentials.participant_tokens[author]`: submit and read that participant's own position.

Send credentials using `Authorization: Bearer <token>`. Do not send author identity in the request body; the API derives it from the participant credential. The legacy `X-Bridge-Actor` header is ignored. Participant credentials cannot reveal, decide, approve, or administer a task. The owner can administer the task but cannot read sealed participant position bodies before reveal.

Read-only endpoints include `GET /health`, `GET /tasks/{id}`, `GET /tasks/{id}/positions`, and `GET /tasks/{id}/export`. Task data routes require a task-scoped bearer token. The owner and participants can view all position bodies after reveal.

Write endpoints include `POST /tasks`, owner-only `POST /tasks/{id}/participants`, `POST /tasks/{id}/positions`, `POST /tasks/{id}/close`, `POST /tasks/{id}/reveal`, `POST /tasks/{id}/decisions`, `POST /tasks/{id}/approvals`, `POST /tasks/{id}/actions/authorize`, and `POST /tasks/{id}/artifacts`.

## Approval behavior

The authorization endpoint is deliberately conservative: **every action authorization requires an unexpired human approval matching the exact action name, target, and scope**. Read-only GET routes do not call that endpoint. A caller cannot bypass the gate by labelling a consequential operation as `export` or another supposed low-risk action.

A decision marked `requires_approval=true` enters `awaiting_approval`. It requires a separate `decision_acceptance` approval bound to the task ID and decision ID before moving to `approved`. The specific side effect then needs its own approval bound to the exact action name, target, and scope. Artifact attachment for a decision requiring approval also checks that the decision-acceptance approval remains valid. Approval defaults to a 15-minute validity window. The authorization endpoint records permission only; it does not execute external side effects.

## Auditability

The SQLite event log is append-only through database triggers and uses a SHA-256 hash chain. `verify events` checks event hashes, source-event/projection consistency, reconstructed task and decision states, and principal records. This detects ordinary accidental or projection tampering; it is not signed non-repudiation or protection against an administrator who can replace the SQLite database and its schema.

## Security limitations

This remains a trusted, local v0 demonstration:

- The HTTP server binds only to loopback; do not expose it to an untrusted network.
- Task-scoped bearer tokens are random and stored as SHA-256 hashes, but there is no TLS, encryption-at-rest, revocation/rotation workflow, or secure multi-user deployment model.
- Anyone with direct access to the SQLite file or trusted CLI can bypass application-level position filtering.
- The person creating a task receives tokens for required participants once and must distribute them separately. For open tasks with no predefined authors, the owner can issue participant tokens through `POST /tasks/{id}/participants` while collection remains open. The system cannot prove that a named AI model authored a submission.
- The current "human owner" credential is a task-scoped bearer token, not an identity-provider-backed identity.
- No real tool executor consumes authorization results. A future executor must check authorization immediately before each side effect and enforce a capability registry that binds canonical action identifiers to actual tools and targets.

Never use this version to authorize real external side effects or as a production security boundary.

## Next milestones

1. Have independent reviewers inspect the actual implementation and adversarial tests.
2. Add a canonical capability/tool registry and an executor that enforces approval at the point of side effect.
3. Add MCP as a thin transport over the existing service.
4. Add provider adapters with real authenticated identities and explicit manual/automatic submission provenance.
5. Complete security, recovery, concurrency, and operational testing before any remote deployment.

See [the v0 workflow specification](docs/MINIMAL_WORKFLOW_V0.md), the [HTTP API contract](docs/API_CONTRACT_V0.md), and the [Alliance operating contract](CLAUDE.md).
