# Minimal collaboration workflow v0.1

## Purpose

Prove a small collaboration workflow before adding provider integrations, automated orchestration policies, a UI, or scoring. v0.1 adds a local MCP stdio adapter after the core invariants; CLI, HTTP, and MCP all call the same `BridgeService`.

## State model

`collecting` → `ready_to_reveal` → `revealed` → `decided` or `awaiting_approval` → `approved` / `rejected` / `changes_requested` → `implemented`.

A task becomes `ready_to_reveal` when every required author has submitted, or when the owner explicitly closes a non-empty collection. Reveal is rejected until then. A task in `changes_requested` may receive a superseding decision; earlier decisions and their dispositions remain in the history.

`mode` is the position-collection mode (`independent` or `open`). `execution_mode` is a separate Auto/Manual policy preference, defaulting to `manual`. v0.1 persists this choice but does not yet execute actions automatically; protected actions still require human approval.

## Data model

- **Task:** objective, acceptance criteria, collection mode (`independent` or `open`), execution mode (`auto` or `manual`), required author labels, state, current decision.
- **Principal:** task-scoped owner or participant identity, random bearer-token hash, and creation timestamp.
- **Position:** author derived from a participant credential on HTTP; body, content hash, timestamp, and `submission_method=manual`.
- **Decision:** chosen option, rationale, supporting position IDs, considered-not-chosen position IDs, approval requirement, status, and superseded decision link.
- **Approval:** human owner action, exact action name, target, scope, note, and expiry.
- **Artifact:** kind, URI, optional SHA-256, and timestamp.
- **Event:** append-only audit record with a global hash chain.

## Identity and sealed positions

Task creation returns one owner bearer token and one separate participant token for each required author. Only token hashes are stored; raw tokens are returned once and are not included in events or timeline exports. Send them using `Authorization: Bearer <token>`.

On HTTP, author identity is derived from the participant token. A request cannot set or override `author`, and `X-Bridge-Actor` is ignored. Participants can submit and read their own position. The owner can administer the task but cannot read participant content while positions are sealed. Reveal makes the positions visible to all task principals.

Only the owner token can close/reveal a collection, record decisions, approve actions, authorize actions, or attach artifacts. Participants cannot use administrative routes.

The CLI is intentionally a trusted local-owner path. It permits the operator to enter manual author labels and inspect the local database. Direct SQLite access also bypasses application filtering. Therefore this v0 workflow is not protection from a malicious database owner or machine administrator.

Independent analysis still depends on the human distributing participant tokens separately and using independent model sessions without cross-sharing drafts before reveal. The Bridge cannot prove that an external AI model authored a manually relayed position. Provider connections are not present.

## Approval semantics

A decision marked `requires_approval=true` enters `awaiting_approval`. It requires a separate approval with `action_name=decision_acceptance`, `target=task_id`, and `scope=decision_id`; only this exact approval moves the decision to `approved`. Approval records are bound to an exact action name, target, and scope and expire after 15 minutes by default (or at a supplied timezone-aware ISO-8601 expiry).

Every call to `authorize_action` requires a separate matching, unexpired approval for the exact side effect, regardless of the caller-selected action name. The decision-acceptance approval alone cannot authorize a deployment or other side effect. There is no caller-controlled low-risk action-name allowlist. Read-only GET routes do not call `authorize_action`.

A decision that requires approval also requires its valid, unexpired `decision_acceptance` approval before artifact attachment. The authorization endpoint records that a check passed; it does not execute a side effect. A future executor must use canonical tool identifiers and a capability registry, and must call the authorization guard immediately before the actual side effect.

## Events and reproducibility

Events include task creation, principal issuance, position submission, collection close/readiness, reveal, decision, approval, action authorization, and artifact attachment. Events hash their canonical content plus the previous event hash. `verify events` checks the event chain, event-to-projection consistency, principal records, and reconstructs task/decision status from the event sequence.

This detects ordinary event or projection tampering, but is not cryptographic non-repudiation. An administrator able to replace the SQLite file and schema can rewrite the database. The system does not yet store signed checkpoints off-host.

## Acceptance criteria mapping

1. **Sealed positions:** authenticated participant tokens cannot retrieve other participants' bodies before reveal; owner cannot read sealed bodies; attempts to spoof `X-Bridge-Actor` or submit a different author are ineffective.
2. **Preservation:** decisions link supporting and considered-not-chosen positions; export retains both.
3. **Reproducibility:** export includes task, positions, reveal/decision/approval events, and artifact pointers; hash-chain and state-projection verification are tested.
4. **Approval gate:** every authorization request fails without an exact, unexpired approval, regardless of caller-selected action name. Expired approvals cannot authorize actions or an approval-gated artifact attachment.
5. **No fake agent links:** health, exports, CLI output, and docs state that submissions are manual and providers are not connected.

## Explicit non-goals

No remote MCP transport, provider APIs, cryptographic position sealing, identity-provider integration, TLS, encryption-at-rest, token rotation/revocation, multi-tenant remote deployment, automatic conflict summarizer, real tool execution, UI, ranking/scoring, or production security claim.
