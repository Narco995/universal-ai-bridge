# Architecture Decisions — Alliance and Strategy Upgrade

## ADR-001: One shared application core

**Decision:** MCP is the intended primary interface. CLI and REST are adapters over the same application services; transport-specific validation must not duplicate business rules.

**Rationale:** Avoid divergent behavior and duplicated policy enforcement.

**Consequence:** Workflow state, authorization, and domain logic belong in the shared core. The v0 CLI and HTTP API already share `BridgeService`; MCP is deferred until core invariants pass tests.

## ADR-002: Peer collaboration, dynamic task leadership

**Decision:** Agents are provider-neutral participants, not hard-coded permanent roles. Assign one accountable task owner and reviewers dynamically according to task fit, capabilities, and evidence. The human founder retains final acceptance and approval authority.

**Rationale:** Prevent permanent titles from becoming implicit authority and allow all participants to contribute beyond fixed role boundaries.

## ADR-003: Persisted workflow state and audit

**Decision:** Model collaboration as a validated, persisted workflow with append-only decision history, explicit dissent, approval records, and reproducible artifacts. Add resumability, bounded retries, idempotency, and cancellation as execution capabilities are implemented.

**Rationale:** Collaboration must survive process/network interruption without losing decisions or duplicating side effects.

## ADR-004: Independent positions when they matter

**Decision:** Use sealed independent positions for consequential decisions; use open mode for routine work. Preserve raw positions and objections, reveal after required submissions or human close, and retain considered-but-not-chosen positions with each decision.

**Rationale:** Reduce anchoring while avoiding an unnecessary three-agent ceremony on every task.

## ADR-005: Review without hierarchy

**Decision:** Select reviewers dynamically. Review actual diffs, artifacts, and test evidence. Use bounded critique/revision rounds, and do not treat consensus as acceptance.

**Rationale:** Independent verification improves quality without assigning permanent command authority to any model.

## ADR-006: Governance at the tool boundary

**Decision:** Enforce least privilege, action classification, exact action/target/scope approval matching, and expiring approval gates in the bridge rather than relying on prompt wording. v0 uses a conservative low-risk allowlist and requires approval for unknown action names.

**Rationale:** Model instructions cannot serve as authorization controls. The v0 approver identity remains an unauthenticated actor label; secure identity and signed approval credentials are required before remote or multi-user use.

## ADR-007: Evaluation before production claims

**Decision:** Add golden workflow scenarios, contract/security tests, traceability, and explicit release gates. Do not claim runtime security, durability, or production readiness until implemented and tested.

## Adoption order

1. Minimal shared core, persistence, and workflow invariants (v0: SQLite, CLI, and loopback HTTP API).
2. Validate sealed positions, dissent preservation, export reproducibility, and approval enforcement with automated tests.
3. Add authenticated participant identity and stronger approval/tool capability boundaries.
4. Add MCP adapter over the same core; preserve REST as a thin adapter.
5. Add provider adapters and actual multi-agent orchestration only after provider identity, state, and failure semantics are defined.
6. Expand integration, evaluation, recovery, observability, and operational hardening.

## Deferred

- OAuth redesign: intentionally deferred; do not introduce it without a separate decision.
- Cryptographic position sealing: deferred beyond v0; application-level filtering is not encryption.
- External provider connections: not implemented in v0; manual relay provenance must remain explicit.
- Framework migration: do not migrate solely for novelty. Adopt compatible patterns incrementally.
