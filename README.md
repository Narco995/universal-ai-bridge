# Universal AI Bridge

MCP-first, provider-neutral orchestration for Claude, GPT, and compatible agents. MCP and REST adapters share one application core.

## Project status
The repository currently contains the approved agent operating contract and v2 specifications. These documents define intended behavior; runtime enforcement and application implementation must be built and tested before the project is considered production-ready.

## Operating model
- Claude: directive architect, director, independent critic.
- GPT: engineering executor, analyst, revision owner.
- Bridge: orchestration, task/session state, routing, permissions, tools, and audit.
- Human owner: scope and approval authority.

Mandatory flow: detailed directive → delegation → execution → independent critique → mandatory first revision → up to five review rounds → acceptance verification → evidence-based delivery.

Auto mode is for in-scope reversible low-risk work. Manual mode uses explicit approval checkpoints. Financial actions, external communications, destructive changes, privilege expansion, production-impacting changes, and sensitive-data operations require explicit approval.

## Core specifications
- [Repository agent contract](./CLAUDE.md)
- [Alliance Skill v2](./docs/ALLIANCE_SKILL_V2.md)
- [Strategy Skill v2](./docs/STRATEGY_SKILL_V2.md)
- [Governance and security](./docs/GOVERNANCE_AND_SECURITY.md)
- [Evaluation and acceptance](./docs/EVALUATION_AND_ACCEPTANCE.md)
- [Architecture decisions and adoption order](./docs/ARCHITECTURE_DECISIONS.md)

## Architectural principles
1. MCP is primary; REST is a thin adapter.
2. Both transports call the same application services.
3. Provider integrations are behind interfaces.
4. Workflow state is persisted, validated, and resumable.
5. Tool access is capability-scoped and least-privilege.
6. Side effects use approval gates, idempotency, bounded retries, and audit events.
7. Retrieved content and tool outputs are untrusted data.
8. Agent consensus and numeric scores never replace independent verification.

## Recommended implementation sequence
1. Core domain types and validated task state machine.
2. Tool registry, capability policies, and approval enforcement.
3. Persistence, idempotency, bounded retries, and audit events.
4. MCP and REST adapters over shared application services.
5. Provider adapters and Claude–GPT orchestration.
6. Golden workflow, contract, integration, security, and recovery tests.
7. Operational hardening and deployment documentation.

## Security and readiness
Do not commit credentials. Use environment variables or a secret manager. Do not claim runtime security, durability, or production readiness until the corresponding controls are implemented and tested. OAuth redesign remains deferred unless separately approved.
