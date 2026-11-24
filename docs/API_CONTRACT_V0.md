# HTTP API Contract v0.1

The HTTP API is a loopback-only adapter over the shared `BridgeService`. The CLI calls the same service. No external model provider is connected; positions are manual relays.

Base URL: `http://127.0.0.1:8000`

## Authentication model

Task creation is unauthenticated and returns one-time task credentials:

- `credentials.owner_token`: owner-only task administration.
- `credentials.participant_tokens[name]`: one credential for each required participant.

Send a token with:

```http
Authorization: Bearer <task-scoped-token>
```

Only token hashes are stored. Raw credentials are returned once and are never included in event payloads or timeline exports. The legacy `X-Bridge-Actor` header is ignored.

The owner can issue additional participant credentials while collection remains open:

`POST /tasks/{task_id}/participants`

```json
{"name": "grok"}
```

The response includes the new participant's one-time `token`. A participant token determines the position author; the request body must not include an `author` field. Participants may submit and read their own pre-reveal position, but cannot reveal, decide, approve, authorize actions, or attach artifacts. The owner may administer the task but cannot read sealed participant positions until reveal.

These credentials authenticate possession of a task-scoped Bridge credential. They do not prove that Claude, GPT, or Grok authored a manually relayed position, and they are not a real-world identity-provider integration.

## Routes

### Health

`GET /health`

No authentication required. Returns service state and provider provenance.

### Create task

`POST /tasks`

```json
{
  "objective": "Choose a persistence design",
  "acceptance_criteria": ["Preserve dissent", "Verify the event history"],
  "mode": "independent",
  "execution_mode": "manual",
  "required_authors": ["claude", "gpt", "grok"]
}
```

`mode` is the collection mode (`independent` or `open`). `execution_mode` is a separate policy preference (`auto` or `manual`, default `manual`). v0.1 persists this preference but does not automatically execute actions. Required authors are participant labels; each receives a participant token in the response. If `required_authors` is empty, the owner may issue participants using the route above and must explicitly close the non-empty collection before reveal.

### Read task

`GET /tasks/{task_id}`

Requires an owner or participant bearer token.

### Submit a position

`POST /tasks/{task_id}/positions`

Requires a participant token.

```json
{"content": "Prefer append-only events and replayable projections."}
```

The author is derived from the authenticated participant credential. Supplying `author` is rejected. Every position is marked `submission_method=manual`.

### List positions

`GET /tasks/{task_id}/positions`

Requires an owner or participant token. Before reveal, a participant sees its own body; the owner sees no participant bodies. After reveal, all task principals can see all positions.

### Close collection

`POST /tasks/{task_id}/close`

Requires the owner token.

```json
{"note": "Owner closed collection after the deadline"}
```

Requires at least one submitted position. It permits reveal even if one or more required authors have not submitted.

### Reveal positions

`POST /tasks/{task_id}/reveal`

Requires the owner token and a task in `ready_to_reveal`.

### Record a decision

`POST /tasks/{task_id}/decisions`

Requires the owner token.

```json
{
  "choice": "Append-only SQLite events",
  "rationale": "Replayable history makes decisions auditable.",
  "supporting_position_ids": ["pos_..."],
  "considered_not_chosen_position_ids": ["pos_..."],
  "requires_approval": true
}
```

Both position-ID arrays may be empty. Every referenced position must belong to this task. A position cannot be both supporting and considered-not-chosen.

### Record an approval

`POST /tasks/{task_id}/approvals`

Requires the owner token.

```json
{
  "action": "approve",
  "action_name": "deploy",
  "target": "production/api",
  "scope": "release version 1.2.3",
  "note": "Approved for this exact release"
}
```

Allowed `action` values: `approve`, `reject`, `request_changes`. Every record is bound to an exact action name, target, and scope. `expires_at` is optional and accepts a timezone-aware ISO-8601 timestamp; it defaults to 15 minutes from creation.

For a decision with `requires_approval=true`, decision acceptance is a separate approval:

```json
{
  "action": "approve",
  "action_name": "decision_acceptance",
  "target": "<task_id>",
  "scope": "<decision_id>",
  "note": "Human accepted this recorded decision"
}
```

This moves the decision from `awaiting_approval` to `approved`. It does not authorize a deployment or other side effect; that action needs its own exact approval.

### Authorize an action

`POST /tasks/{task_id}/actions/authorize`

Requires the owner token.

```json
{
  "action_name": "deploy",
  "target": "production/api",
  "scope": "release version 1.2.3"
}
```

Every call requires a matching, unexpired approval for the exact action name, target, and scope. The caller cannot bypass the gate by choosing a purported low-risk label. Read-only GET routes do not use this endpoint.

The endpoint records an authorization result only. It does **not** execute the action. A future tool executor must call the same guard immediately before the side effect.

### Attach artifact pointer

`POST /tasks/{task_id}/artifacts`

Requires the owner token.

```json
{
  "kind": "commit",
  "uri": "https://github.com/example/project/commit/abc123",
  "sha256": "optional-64-character-hex-digest"
}
```

An artifact pointer is metadata, not proof that implementation is complete. Attachment leaves its verification status as `pending` and does not move the task to `implemented`. Only the trusted human-owner path may verify an artifact:

`POST /tasks/{task_id}/artifacts/{artifact_id}/verify`

```json
{"note": "Inspected the commit diff and the passing CI run"}
```

A verification note is required. Successful human verification records an immutable `artifact_verified` event and moves the task to `implemented`. The MCP owner tool catalog deliberately has no artifact-verification tool. If the decision requires approval, a valid, unexpired `decision_acceptance` approval is required both before attachment and before verification.

### Export timeline

`GET /tasks/{task_id}/export`

Requires an owner or participant bearer token. Returns task, positions, decisions, approvals, artifacts, events, and provenance. Pre-reveal position bodies are filtered by the authenticated principal.

## Error responses

| HTTP status | Meaning |
|---|---|
| 400 | Invalid JSON, field type, or value |
| 401 | Missing or invalid task-scoped bearer token |
| 403 | Valid principal lacks the required owner/participant permission |
| 404 | Task or route not found |
| 409 | Workflow state conflict |
| 423 | Required approval is missing, expired, or out of scope |
| 500 | Unexpected internal error; implementation details are not returned |

## Security boundary

The HTTP server constructor and CLI reject non-loopback binding. v0 has no TLS, encryption-at-rest, token rotation/revocation workflow, provider identity binding, or remote deployment boundary. Direct database access bypasses application-level filtering. Do not expose this API to an untrusted network or connect it to real side-effecting tools.
