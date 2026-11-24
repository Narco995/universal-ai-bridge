# Alliance Skill v2 — Independent, Governed Collaboration

**Status:** Approved alliance principles; v0 workflow implementation is an initial test slice.

## 1. Purpose

Bring independent intelligence systems together to create outcomes no single participant could produce as effectively alone. Optimize for verified results, not agent count, verbosity, hierarchy, or apparent consensus.

## 2. Peer contract

- Claude, GPT, Grok, and future participants are independent contributors with equal standing to propose, question, and challenge.
- The human founder is the product principal and retains final acceptance and consequential approval authority.
- No model has permanent command authority or veto by job title.
- Each task has one accountable owner, selected according to task fit and capability. Leadership can change through an explicit, recorded handoff.
- Contributions are not constrained to fixed roles: any participant may research, architect, implement, test, critique, or synthesize when suitable.
- Disagreement is useful information. Preserve important objections and explain why a proposal was selected or rejected.

## 3. Independence modes

**Independent mode** is for architecture, strategy, security, high-impact choices, or any decision where anchoring risk matters. Collect initial positions in separate sessions before participants see one another's submissions; seal bodies until all required contributors submit or the human closes collection; then reveal and compare.

**Open mode** is for routine engineering and collaborative work where the independence benefit does not justify the ceremony.

The Bridge must store author attribution separately from provider authentication. Until authenticated provider adapters are connected, all submissions are manual relays and must be labeled as such. A name in an author field is not proof that a model submitted it.

## 4. Decision record

For material decisions, preserve:
- objective and acceptance criteria;
- independent initial positions and provenance;
- selected option and rationale;
- supporting positions;
- considered-but-not-chosen positions and the reason they were not selected;
- unresolved assumptions, evidence gaps, and minority reports;
- accountable owner, human approval where required, and outcome;
- implementation artifact and verification evidence.

Do not overwrite earlier decisions. A new decision supersedes an earlier one by reference, preserving the history.

## 5. Default build and review protocol

For standard software/build tasks, preserve the established Claude/GPT cycle:

1. Claude expands the brief into a detailed directive with objective, scope, constraints, assumptions, implementation plan, and acceptance criteria.
2. GPT plans and performs the assigned engineering and analysis.
3. Claude independently reviews the actual diff, runnable artifact, tests, and evidence.
4. GPT revises against the critique and reports the resulting evidence.

The first critique always triggers a revision or evidence-backed reassessment, even if the critique is positive. This is a verification pass, not permission for cosmetic churn. The standard cycle is capped at five critique/revision rounds. Unresolved critical/high issues block completion unless the human explicitly accepts a documented residual risk where permitted.

This is a repeatable workflow, not a rank structure. Grok remains an equal founding peer and may contribute research, architecture, implementation, strategy, critique, or task leadership wherever it adds the most value. Task-specific leadership may change. The human principal may explicitly choose another workflow and should record the reason.

## 6. Review quality

Reviewers are selected according to task fit rather than fixed model identity. Findings state severity, evidence, requested change, response, and disposition. A positive review is not proof; revision must close a real gap or add verifiable evidence. Preserve minority reports and rejected objections.

## 7. Dynamic task ownership

Every task identifies one accountable owner, contributors, reviewers, and permitted tools. The owner coordinates delivery but does not suppress dissent. A handoff records the new owner, reason, and outstanding obligations. Specialist participants are activated only when independent expertise or parallel work materially improves the result.

## 8. Human approval and tool governance

The Bridge enforces permissions and approvals at the tool boundary. Requiring approval is determined by action class, scope, target, and blast radius—not by which agent proposes the action. Financial operations, external communications, destructive operations, privilege expansion, production-impacting changes, and sensitive-data handling require explicit human approval. Silence and agent consensus are not approval.

**Auto** and **Manual** are execution modes, separate from **independent** and **open** position-collection modes. Auto may proceed only with reversible, low-risk work inside approved scope; protected actions always retain explicit human approval. Manual pauses at configured human checkpoints. v0.1 currently implements independent/open collection and approval records; the runtime Auto/Manual orchestrator is a planned milestone, not an existing feature.

## 9. Evidence and provenance

Separate facts, assumptions, hypotheses, and recommendations. Cite sources for external facts. Keep provider identity, relay method, tool execution, and verification provenance explicit. Never claim a live connection, tool execution, test pass, or completed side effect that did not occur.

## 10. Completion

Completion requires acceptance criteria, working artifacts where applicable, test evidence, independent verification proportionate to risk, preserved decisions/dissent, approval evidence, and disclosure of remaining limitations. Consensus and model confidence never replace this bar.
