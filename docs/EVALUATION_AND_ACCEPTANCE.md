# Evaluation and Acceptance Specification

**Status:** Approved operating specification.

## 1. Principle
Agent agreement, confidence, or a weighted score is never sufficient for acceptance. Completion requires observable evidence against predeclared criteria.

## 2. Evaluation layers
1. Unit tests: state machine, schemas, policy checks, retry/idempotency logic, context assembly.
2. Contract tests: MCP and REST adapters invoke the same core behavior and return equivalent domain results.
3. Integration tests: provider adapters, persistence, tool routing, session resume, cancellation.
4. Workflow tests: directive expansion, delegation, mandatory first critique revision, five-round cap, Auto/Manual approvals.
5. Security tests: prompt injection, tool scope escalation, secret redaction, malformed inputs, unsafe destinations, approval bypass.
6. Operational tests: timeouts, transient failure, rate limits, process restart, duplicate delivery, partial failure.
7. Regression/evaluation sets: representative tasks with expected outcomes and rubric-based grading.

## 3. Required golden scenarios
- Short brief is expanded into a detailed directive before delegation.
- First critique triggers a revision even if the first review is positive.
- Review round count never exceeds five.
- Unresolved blocking finding after round five prevents completion.
- Agent consensus without passing acceptance checks does not complete a task.
- Auto mode performs an in-scope reversible edit but pauses before an external communication or destructive action.
- Manual mode waits for explicit approval at configured checkpoints.
- Approval for one target cannot authorize a different target.
- Prompt injection inside a retrieved document cannot change system policy or tool permissions.
- Transient failure retries within budget; permanent failure does not retry indefinitely.
- Duplicate delivery of an idempotent request does not duplicate side effects.
- Process restart resumes from persisted state without repeating completed non-idempotent actions.
- MCP and REST paths share the same application service and business logic.
- Secrets are absent from logs, traces, prompts, and test artifacts.

## 4. Suggested evaluation dimensions
Optional task-specific scorecard: task completion 25%; technical correctness 20%; independent verification 20%; instruction compliance 15%; security and reliability 10%; efficiency 10%.

Strategy evaluations should separately assess objective alignment, evidence quality, feasibility, risk management, resource efficiency, and measured outcomes. Do not compare raw scores across unrelated task classes.

## 5. Release gates
A release candidate must pass required unit, contract, integration, and security tests; have no unresolved critical/high defects; include completed independent review; demonstrate state persistence and safe resume for supported workflows; demonstrate approval enforcement for protected actions; and document known limitations and operational prerequisites.

## 6. Traceability
For each task, link objective → directive → acceptance criteria → implementation change → test evidence → review finding → final disposition.

## 7. Reporting
Report exact commands and pass/fail outcomes. If a test was not run, say so. Never fabricate coverage, benchmark results, or production readiness.
