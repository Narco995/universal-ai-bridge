# Skill pack audit and integration notes

**Prepared:** 2026-11-27  
**Pack version:** 3.0.0  
**Source:** Four user-supplied skill bundles: \`android-mobile-eng.skill\`, \`claud-uiux-pro.skill\`, \`vibekit-agent.skill\`, and \`web-performance-architect.skill\`.

## Scope

The source bundles were unpacked and reviewed. The first three were nested ZIP skill bundles containing a \`SKILL.md\`; the web-performance bundle also contained three references and an HTML audit script. The revised skills are stored under \`.claude/skills/\`.

## Findings retained

- iPhone-first workflows and remote cloud development.
- Safari userscript and Android WebView coverage.
- Headless-first UI architecture, design tokens, accessibility, and cognitive UX.
- Agent lifecycle, orchestration patterns, provider abstraction, memory, budgets, and error handling.
- Core Web Vitals, rendering, image/bundle optimization, query design, safe caching, queues, and CDN fundamentals.

## High-priority corrections

1. **iPhone/Claude Code mismatch:** the original mobile skill presented Claude Code remote-control flows as if they were a standard iPhone capability. The revised skill distinguishes Claude web/mobile from a separate remote computer session and does not require Claude Code on iPhone.
2. **Unverified Vibekit APIs:** source examples such as \`BaseSkill\`, \`Pipeline\`, \`ParallelSkills\`, \`JSONMemory\`, and \`MultiProviderSkill\` were not independently verified. The revised skill treats them as unverified and defines framework-neutral patterns.
3. **Model identifiers:** fixed model IDs and fallback chains can become invalid or unavailable. Model/provider identifiers remain runtime configuration and require compatibility checks.
4. **Reasoning policy:** instructions to expose or universally request hidden chain-of-thought were removed. Use concise plans, assumptions, evidence, and conclusions.
5. **Agent error handling:** success-shaped degradation and "never crash" guidance was replaced by explicit failed, timed-out, cancelled, and approval-required states.
6. **Mobile build tooling:** legacy \`dx\` guidance was replaced with current supported Android Gradle/D8/R8 toolchain selection. Termux is limited to Android and should use virtual environments.
7. **WebView origin checks:** complete origin validation must include scheme, hostname, and port, with redirect checks and minimal JavaScript bridges.
8. **Web cache safety:** caching guidance now covers private responses, cookies, \`Set-Cookie\`, tenant isolation, and cache keys.
9. **Redis lock correctness:** lock release must use owner-token compare-and-delete; fencing is needed when stale workers can write. Unconditional lock deletion is unsafe.
10. **Performance claims:** static HTML heuristics, lab measurements, field data, and backend traces are explicitly distinguished.

## Integration contract

The central \`uab-workstation-operator\` skill is the operational reference for Box, GitHub, MCP, Claude web/iPhone, approvals, and preservation. Specialist skills are loaded only when relevant. Root \`CLAUDE.md\`, the Alliance v2 contract, and the governance/security specification remain authoritative where instructions overlap.

The pack does not provide remote MCP, OAuth, provider API adapters, an autonomous execution engine, or a production security boundary. Skills do not grant permissions or install connectors.

## HTML audit script limitations

\`web-performance-architect/scripts/audit_html.py\` is a static markup heuristic. It cannot measure LCP, INP, CLS, runtime behavior, network waterfalls, accessibility, or security. The first image in source order is not necessarily the LCP element. Use Lighthouse, browser traces, and representative field data for those claims.

## Not introduced

- No hard-coded Claude/GPT/Gemini model IDs.
- No unverified Vibekit API claims.
- No unrestricted shell/browser tools or default autonomous approval.
- No database, cache, queue, or orchestration framework migration.
- No claim that the HTML script proves Core Web Vitals or security.
