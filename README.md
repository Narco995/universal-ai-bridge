# Universal AI Bridge

A provider-neutral collaboration system for Claude, GPT, Grok, and compatible intelligence systems. Its long-term architecture is MCP-first, with transport adapters sharing one application core.

## Current status

The implementation branch contains a **minimal collaboration workflow v0**: a Python standard-library service, SQLite store, CLI, loopback-only HTTP API, and automated tests. This slice proves selected workflow invariants; it is not a production multi-agent platform and does not connect to external model providers. Claude/GPT/Grok positions are currently submitted manually by the human operator.

## Alliance principles

- Independent intelligence, equal intellectual respect, and the freedom to disagree.
- Roles are task-specific responsibilities, not permanent authority or a chain of command.
- Leadership follows the problem and relevant capability; every participant may propose, build, research, or critique.
- Important dissent and rejected proposals remain linked to the decision record.
- Independent positions are collected before reveal when the decision warrants it; routine work uses a lighter open mode.
- The human founder remains the final acceptance and approval authority.
- Evidence, tests, and working artifacts—not model consensus—determine technical acceptance.

## Existing operating specifications

- [Repository agent contract](./CLAUDE.md)
- [Alliance Skill v2](./docs/ALLIANCE_SKILL_V2.md)
- [Strategy Skill v2](./docs/STRATEGY_SKILL_V2.md)
- [Governance and security](./docs/GOVERNANCE_AND_SECURITY.md)
- [Evaluation and acceptance](./docs/EVALUATION_AND_ACCEPTANCE.md)
- [Architecture decisions and adoption order](./docs/ARCHITECTURE_DECISIONS.md)

## Run locally

Requires Python 3.10 or newer. No third-party runtime dependencies are required.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

Create a task and collect independently submitted positions:

```bash
uab --db ./bridge.sqlite3 task create \\
  --objective "Choose a persistence design" \\
  --criteria "Preserve dissent" \\
  --criteria "Block unapproved consequential actions" \\
  --mode independent \\
  --required-author claude \\
  --required-author gpt

uab --db ./bridge.sqlite3 position submit TASK_ID --author claude --content "Append-only SQLite events"
uab --db ./bridge.sqlite3 position submit TASK_ID --author gpt --content "Mutable JSON snapshots"
uab --db ./bridge.sqlite3 task reveal TASK_ID

uab --db ./bridge.sqlite3 decision record TASK_ID \\
  --choice "Append-only SQLite events" \\
  --rationale "Replayable history is required" \\
  --supporting POSITION_ID \\
  --considered-not-chosen OTHER_POSITION_ID \\
  --requires-approval

uab --db ./bridge.sqlite3 approval TASK_ID --action approve \
  --action-name "modify_shared_infrastructure" \
  --target "repository/main" \
  --scope "change collaboration workflow" \
  --note "Reviewed by the human principal"
uab --db ./bridge.sqlite3 action TASK_ID --name "modify_shared_infrastructure" \
  --target "repository/main" --scope "change collaboration workflow"
uab --db ./bridge.sqlite3 export TASK_ID --format markdown --output task-TASK_ID.md
uab --db ./bridge.sqlite3 verify events
```

`task reveal` is accepted when all required authors have submitted or a human has explicitly closed collection with `task close`.

Start the HTTP API (loopback only):

```bash
uab --db ./bridge.sqlite3 serve --host 127.0.0.1 --port 8000
```

Routes: `POST /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/positions`, `GET /tasks/{id}/positions`, `POST /tasks/{id}/close`, `POST /tasks/{id}/reveal`, `POST /tasks/{id}/decisions`, `POST /tasks/{id}/approvals`, `POST /tasks/{id}/actions/authorize`, `POST /tasks/{id}/artifacts`, and `GET /tasks/{id}/export`.

## Security boundary — important v0 limitation

Position `author` values and the `X-Bridge-Actor` header are attribution/viewer labels, **not authenticated provider or human identities**. The server is loopback-only and is intended for a trusted single-user local demonstration. A caller able to reach it can claim another actor label; direct database access bypasses application filtering. Therefore, v0 demonstrates the sealing and approval *workflow logic* under a trusted identity assumption, not adversarial multi-user access control. Do not expose it to an untrusted network or use it to authorize real external side effects.

There is no user authentication, TLS, encryption-at-rest, cryptographic participant identity, or signed approval credential. The `authorize` route records an authorization result only; it does not execute an external side effect. Before external or multi-user use, add authenticated participant identities, protected approval credentials, capability-scoped tool adapters, and independent security tests.

## v0 scope and guarantees

- Independent mode hides other authors' position bodies through the application API until reveal when the caller identity is trusted; open mode exposes them immediately.
- Each author label may submit once per task. Submissions are marked `manual` until real provider adapters exist.
- Dissent is stored as position IDs explicitly linked under `considered_not_chosen_position_ids` in a decision.
- Timeline export includes task, positions, decisions, approvals, artifacts, and task events.
- Events are append-only at the SQLite layer and form a SHA-256 hash chain; `verify events` checks the chain and compares event records with task, position, decision, approval, and artifact projections. This detects ordinary projection tampering but is not a signed or tamper-proof audit system against an administrator who can replace the database.
- The action authorization policy is conservative: only the explicit low-risk names `read`, `list`, `inspect`, `export`, `status`, and `analyze` are allowlisted without approval. Unknown and consequential action names require approval even if a decision's `requires_approval` flag is false. Approval is bound to an exact action name, target, and scope, and expires after 15 minutes by default. A decision marked `requires_approval` additionally requires an approved record before artifact attachment. Identity of the approver is not authenticated in v0.
- The REST API calls the same `BridgeService` methods as the CLI. MCP is intentionally deferred until these core invariants pass tests.

See [the v0 workflow design](docs/MINIMAL_WORKFLOW_V0.md) for state transitions, API contract, limitations, and acceptance-test mapping.
