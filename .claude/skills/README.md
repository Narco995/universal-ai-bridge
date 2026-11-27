# Universal AI Bridge skills

This folder contains the repository-managed skill source for the Universal AI Bridge ecosystem.

## Skills

- \`uab-workstation-operator\`: Box, repository, MCP, Claude web/iPhone, permissions, preservation, and orchestration boundaries.
- \`android-mobile-eng\`: mobile-first development, iOS Safari, Android WebView, ADB, and Termux.
- \`claud-uiux-pro\`: product UX, design systems, responsive UI, accessibility, and interface reviews.
- \`vibekit-agent\`: framework-neutral agent engineering, provider adapters, orchestration, memory, and tool security.
- \`web-performance-architect\`: Core Web Vitals measurement, frontend, backend, cache, lock, and CDN performance.

## Loading and precedence

- The root \`CLAUDE.md\` is the repository-level operating contract.
- Use the central workstation operator skill for Box, repository, MCP, permission, or multi-agent workstation tasks.
- Load a specialist skill only when it materially applies to the task.
- The repository operating contract and \`docs/GOVERNANCE_AND_SECURITY.md\` take precedence over specialist advice if there is a conflict.
- A skill is guidance, not a permission grant, service, provider connection, or MCP server.

## Claude web and mobile

The \`.claude/skills\` directory is repository-managed source and can be consumed by compatible repo-aware agents. It does not automatically install custom Skills into Claude web/iOS. Import the relevant skill package using the target product's supported Skills workflow, and configure MCP separately. No Claude Code installation is required on iPhone.

## Runtime boundaries

These skills do not change the current v0.1 runtime boundaries: provider APIs are not connected, position submissions are manual relays, the HTTP API is loopback-only, MCP is local stdio, and remote MCP/OAuth remain deferred. Do not infer that a documented target capability is already implemented.
