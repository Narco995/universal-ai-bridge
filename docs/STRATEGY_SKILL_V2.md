# Strategy Skill v2 — Decision Intelligence and Execution Planning

**Status:** Approved operating specification.

## 1. Purpose
Convert ambiguous objectives into evidence-based, feasible, measurable plans and continuously compare outcomes against intent.

## 2. Strategic analysis sequence
1. **Frame:** define desired outcome, stakeholder, time horizon, and measurable success condition.
2. **Baseline:** inspect current system, assets, constraints, and prior decisions. Cite the source of baseline facts.
3. **Research:** prefer primary documentation, standards, source repositories, and first-party data. Record source date, relevance, and confidence. Seek contrary evidence for consequential decisions.
4. **Classify:** label material statements as Fact (directly supported), Assumption (provisionally accepted), Hypothesis (testable prediction), or Recommendation (proposed action).
5. **Map constraints:** identify budget, time, technical dependencies, privacy, security, legal, operational, and approval constraints.
6. **Generate options:** include a baseline/no-change option when useful; avoid false breadth.
7. **Evaluate:** compare feasible options using explicit criteria and task-appropriate weights.
8. **Decide:** recommend one feasible option, explain trade-offs, confidence, and rejected alternatives.
9. **Plan:** define ordered milestones, owners, dependencies, risks, rollback/recovery, and acceptance tests.
10. **Execute:** work in bounded stages; re-evaluate when evidence or assumptions change.
11. **Verify:** measure actual results against baseline and acceptance criteria.
12. **Learn:** capture reusable decisions and update the plan when outcomes diverge.

## 3. Decision matrix
Choose criteria relevant to the task. Typical criteria: outcome fit/user value, technical correctness, security/privacy, feasibility/time-to-value, maintainability/reversibility, total cost of ownership, reliability/operational burden, latency/performance.

Weights must sum to 100% when numeric weighting is used. Scores are decision aids, not evidence. Explain material uncertainty and run sensitivity checks when small weight changes could change the winner.

## 4. Research quality
Prefer primary sources. Check publication/update dates for time-sensitive claims. Corroborate critical claims with independent sources where practical. Record disagreements and unresolved uncertainty. Do not present search snippets as conclusive evidence. Distinguish observed evidence from inferred conclusions. Cite source URLs and access dates in research artifacts. Never claim research was performed when no source was inspected.

## 5. Risk analysis
For each material risk record description and trigger, likelihood and impact, severity, mitigation and contingency, owner, residual risk, and approval requirement. Consider failure modes, abuse cases, prompt injection, tool misuse, data exposure, provider outages, rate limits, cost overruns, and lock-in.

## 6. Execution planning
Each work package includes deliverable and owner, dependencies, estimated effort or bounded time budget, acceptance criteria, test/verification method, rollback or recovery path, status, and evidence.

Prefer small, reversible increments. Do not bundle unrelated changes into one release.

## 7. Replanning triggers
Reassess when a core assumption is disproven, a dependency/provider capability changes, a critical/high risk materializes, cost/latency/timeline exceeds bounds, acceptance tests reveal a design flaw, or user scope/approval changes. Preserve decision history; do not silently rewrite prior decisions.

## 8. Strategy deliverable
Include executive recommendation; objective and baseline; evidence and source quality; facts, assumptions, and hypotheses; options and comparison criteria; recommended approach and trade-offs; milestones and acceptance criteria; risks, mitigations, and approvals; confidence and unresolved questions; measurement and learning plan.
