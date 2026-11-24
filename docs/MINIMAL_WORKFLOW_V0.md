# Minimal collaboration workflow v0

## Purpose

Prove the smallest useful collaboration workflow before introducing MCP adapters, model-provider integrations, a UI, orchestration policies, or scoring. The CLI and HTTP API both call BridgeService; workflow rules live in one core.

## State model

`collecting` → `ready_to_reveal` → `revealed` → `decided` or `awaiting_approval` → `approved` / `rejected` / `changes_requested` → `implemented`.

A task becomes `ready_to_reveal` automatically when every required author has submitted, or when the human explicitly closes a non-empty collection. `reveal` is rejected until that condition is met. A task in `changes_requested` may receive a superseding decision; earlier decisions remain in the record.

## Data model

- **Task:** objective, acceptance criteria, mode, required author labels, state, current decision.
- **Position:** author label, body, content hash, timestamp, and `submission_method=manual`.
- **Decision:** chosen option, rationale, supporting position IDs, considered-not-chosen position IDs, approval requirement, status, and superseded decision link.
- **Approval:** human actor label, approve/reject/request-changes action, exact action name, target, scope, note, and timestamp.
- **Artifact:** kind, URI, optional SHA-256, timestamp.
- **Event:** append-only audit record with a global hash chain.

## Independence and provenance

In independent mode, a caller sees its own position body while collection is sealed; other authors' bodies become visible after reveal. In open mode, bodies are visible immediately. The HTTP server is loopback-only in v0. The `X-Bridge-Actor` header is a caller-supplied label, not authenticated identity; this filtering is a workflow demonstration, not a security boundary against an untrusted caller. Database-file access also bypasses application filtering. Independent analysis still depends on the human operator using separate model sessions and not cross-sharing drafts before submission. All submissions are explicitly recorded as manual; no live provider connection is claimed.

## Approval semantics

A decision marked `requires_approval=true` enters `awaiting_approval`. The application accepts approval only with the `human` actor label, but that label is not authenticated in v0. Every approval is bound to an exact action name, target, and scope; an approval for one target or scope cannot authorize another. Approvals expire after 15 minutes by default; an explicit timezone-aware ISO-8601 expiry can be supplied. The conservative default policy allowlists only `read`, `list`, `inspect`, `export`, `status`, and `analyze` as low-risk actions. Every other action name requires a matching, unexpired approval even when the decision flag is false. A decision marked `requires_approval=true` also requires an approved record before artifact attachment. The v0 authorization endpoint records that the check passed but does not execute the requested action. A future tool executor must call the same guard immediately before a side effect, using authenticated identity, capability policy, idempotency, and an audit trail.

## Events and reproducibility

Events include task creation, position submission, collection close/readiness, reveal, decision, approval, action authorization, and artifact attachment. Event rows cannot be updated or deleted through normal SQL operations, and each event hashes its canonical content plus the previous event hash. `verify events` also compares task, position, decision, approval, and artifact projections with their originating events. This detects ordinary event and projection tampering but is not cryptographic non-repudiation: an administrator able to replace the SQLite file can rewrite the chain and projections.

## Acceptance criteria mapping

1. **Sealed positions:** service and HTTP tests verify that author A cannot retrieve author B's body in independent mode before reveal, and can after reveal.
2. **Preservation:** decision records contain the selected and considered-not-chosen position IDs; export keeps both.
3. **Reproducibility:** export contains task, positions, reveal/decision/approval events, and artifact pointers; hash-chain verification is tested.
4. **Approval gate:** consequential/unknown actions fail without an exact action-target-scope approval, even when a caller omits the decision-level approval flag; mismatched approval scope remains blocked.
5. **No fake agent links:** health, exports, CLI output, and docs state that submissions are manual and providers are not connected.

## Explicit non-goals

No cryptographic position sealing, provider authentication, multi-tenant access control, remote deployment, MCP adapter, automatic conflict summarizer, real tool execution, UI, ranking/scoring, or production security claim.
