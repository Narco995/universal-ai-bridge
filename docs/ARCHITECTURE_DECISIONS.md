# Architecture Decisions — Alliance and Strategy Upgrade

## ADR-001: MCP-first, shared application core
**Decision:** MCP is the primary interface. REST remains a thin compatibility/API adapter. Both call the same application services and domain logic.

**Rationale:** Prevent divergent behavior and duplicate policy enforcement.

**Consequences:** Transport adapters may validate protocol-level input, but authorization, task lifecycle, tool policy, and business rules belong in the shared core.

## ADR-002: Agent-neutral orchestration
**Decision:** Claude and GPT are configured roles behind provider/model adapters, not hard-coded assumptions in domain logic.

**Rationale:** Allow provider changes and specialist expansion without redesigning the core.

## ADR-003: Persisted workflow state
**Decision:** Model collaboration as a validated, persisted state machine with resumable execution, bounded retries, idempotency, cancellation, and audit events.

**Rationale:** Long-running agent workflows must survive process/network interruption without unsafe duplicate side effects.

## ADR-004: Mandatory review protocol
**Decision:** Claude authors/expands directives and independently critiques GPT's work. The first critique always triggers revision. Maximum five rounds. Acceptance is evidence-based.

## ADR-005: Dynamic specialist routing
**Decision:** Activate specialist agents only when the task has separable work or a meaningful need for independent expertise. Default to one executor and one independent reviewer.

## ADR-006: Governance at the tool boundary
**Decision:** Enforce least privilege, action classification, scope validation, and approval gates in the bridge rather than relying on prompt wording.

## ADR-007: Evaluation before production claims
**Decision:** Add golden workflow scenarios, contract/security tests, traceability, and explicit release gates. Do not claim runtime security, durability, or production readiness until implemented and tested.

## Adoption order
1. Repository instructions and skills (this change).
2. Core domain types and state machine.
3. Tool registry, permission and approval enforcement.
4. Persistence, idempotency, retries and audit events.
5. MCP and REST adapters over the same core.
6. Workflow orchestration and provider adapters.
7. Evaluation suite and operational hardening.

## Deferred
- OAuth redesign: intentionally deferred; do not introduce it as part of this upgrade without a separate decision.
- Framework migration: do not migrate solely for novelty. Adopt compatible patterns incrementally.
