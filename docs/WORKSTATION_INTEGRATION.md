# Workstation and Claude integration map

**Status date:** 2026-11-27

## Component boundaries

| Component | Intended responsibility | Current boundary |
|---|---|---|
| Claude web/iPhone | User-facing reasoning, task initiation, review, and human approval | Not a remote shell or local Claude Code runtime |
| Simular Box | Persistent cloud workstation and local development host | Existing Box data and projects must be preserved |
| Universal AI Bridge | Task state, identity, decisions, approval records, audit history, and transport adapters | v0.1 Python/SQLite workflow; no model provider APIs connected |
| MCP | Model-to-tool interface | Current documented transport is local stdio |
| HTTP API | Thin adapter over the shared service core | Loopback-only; not safe to expose as a public endpoint |
| Skills | Reusable task guidance | No execution capability, authentication, or permission is granted by a skill |

## Current UAB runtime boundaries

The v0.1 implementation and its specifications describe:
- a SQLite-backed shared \`BridgeService\`;
- CLI, loopback HTTP, and local MCP stdio adapters;
- task-scoped owner and participant credentials;
- manually relayed positions rather than verified provider submissions;
- persisted Auto/Manual preference, not a completed autonomous execution engine;
- action-authorization checks that record an authorization decision but do not execute a real side effect;
- no remote MCP Streamable HTTP endpoint, OAuth deployment, or public network boundary.

Do not describe remote Claude web/iPhone tool access, automated Claude/GPT provider routing, or real-world action execution as operational until each is separately implemented, deployed, authenticated, and tested.

## Skill installation

The canonical repo-managed skills live in \`.claude/skills/\`. A compatible repository agent can use them from this checkout. The workstation copy can be installed into \`/workspace/abinath-ai-workstation/skills/\` using:

\`\`\`bash
python scripts/install_workstation_skills.py \
  --source .claude/skills \
  --destination /workspace/abinath-ai-workstation/skills
\`\`\`

The installer is additive: it creates missing files and refuses to overwrite differing files. Review conflicts manually rather than forcing an overwrite.

Claude web/mobile custom Skill installation is a separate user-facing product workflow. These repository files do not automatically appear in Claude web/iOS. MCP configuration is also separate and must use a reachable authenticated remote endpoint supported by the target client. The user completes sign-in, OAuth consent, MFA, and connector approval themselves.

## Security follow-up before an executor

The initial code review identified an approval-replay defect: the v0.1 authorization path could reuse a valid exact-scope approval until expiry. A proposed correction has now been added to draft PR #1 at commit `0044711` (branch `feature/minimal-collaboration-v0`).

The proposed correction adds a nullable `consumed_at` migration, atomically consumes an exact action approval inside the existing SQLite `BEGIN IMMEDIATE` transaction, records an `approval_consumed` event linked to `action_authorized`, and verifies the consumed projection against the event chain. Regression tests cover replay, concurrent requests (exactly one succeeds), legacy schema migration, and consumed-state tampering. Local verification passed 49 tests and Ruff; GitHub Actions for Python 3.10–3.13 were queued when this note was updated.

**Status:** the fix is proposed, not merged. The `main` branch does not yet contain it. Do not describe the mainline runtime as replay-protected until PR #1 is reviewed, merged, and its CI matrix passes. This skills/documentation PR itself remains a documentation/skills change and does not introduce a side-effect executor.

## Preservation and change management

- Do not reset, rebase, or clean an existing project checkout to make it match GitHub.
- Use isolated worktrees or separate directories where local changes exist.
- Save a Box snapshot before consequential workstation changes.
- Do not upgrade the Box image as part of a skill installation.
- Do not store credentials in repository files or skill text.
