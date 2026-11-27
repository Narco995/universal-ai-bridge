---
name: android-mobile-eng
description: |
  Mobile-first engineering for Android, iOS Safari, userscripts, mobile
  browser workflows, Termux, remote development environments, and secure
  WebView applications. Use when building or debugging mobile software.
---

# Android and Mobile Engineering

## Operating principles

- Treat mobile as a constrained client, not as the place to run every server workload.
- Prefer remote cloud development for heavy builds and agent execution when the phone is the user's primary device.
- Do not assume an iPhone can run Android Termux, Linux services, or desktop Claude Code.
- Distinguish Claude mobile/web access from a remote-control session to a separate computer.
- Keep mobile workflows usable with touch, small screens, unreliable networks, and interrupted sessions.

## Choose the right execution environment

| Work | Preferred environment |
|---|---|
| Claude conversation and review | Claude web or iPhone app |
| Remote tool use | User-authorized remote MCP connector |
| Heavy builds, tests, browser automation | Approved cloud workstation or Codespace |
| Android device debugging | Android device + authorized ADB host |
| iOS Safari enhancement | Safari extension or userscript supported by the selected app |
| Small Android-side scripts | Termux, where supported |
| iOS local shell experiments | iSH limitations apply; do not assume full Linux compatibility |

Do not prescribe Claude Code as an iPhone installation prerequisite. If a workflow requires a desktop agent, explain that it runs on the remote computer and the phone is only the control surface.

## Android WebView security

- Enable JavaScript only when the application requires it and only for trusted content.
- Disable file and content access unless a documented feature requires them.
- Disallow mixed content.
- Keep cleartext traffic disabled.
- Validate the complete origin: scheme, hostname, and port. A hostname-only comparison is insufficient.
- Validate every navigation and redirect; open external destinations in the system browser.
- Avoid \`addJavascriptInterface\`. If unavoidable, expose a minimal, audited API to trusted first-party content only.
- Use Android Network Security Config for explicit trust rules.
- Handle safe browsing, TLS errors, downloads, intents, and external schemes deliberately.
- Never proceed past certificate errors in production.

## Android build and signing

- Prefer current Android Gradle Plugin, Gradle wrapper, Android SDK Build Tools, and D8/R8 toolchain supported by the project's target SDK.
- Do not recommend legacy \`dx\` workflows for new projects.
- Pin toolchain versions and use Gradle dependency verification where practical.
- Debug signing is for local testing only. Release signing keys belong in protected CI secrets or a secure signing service.
- Never put keystores or passwords in Git, chat, or build logs.
- Verify APK/AAB signatures, package ID, permissions, target SDK, and artifact provenance before distribution.
- Build on a supported Linux/macOS/Windows environment; Termux-only builds are an optional constrained path, not the default production toolchain.

## ADB safety

- Use USB or Android's authenticated wireless debugging pairing flow.
- Do not expose legacy unauthenticated ADB over a public or shared network.
- Verify the device serial before install, uninstall, shell, or file transfer.
- Treat \`adb shell\`, \`install\`, \`uninstall\`, and \`push\` as consequential device operations; confirm target and intent.
- Redact device identifiers and private paths in reports.

## iOS Safari userscripts and extensions

- Scope \`@match\` to the minimum required domains; never default to all websites without a clear reason.
- Request only required userscript grants.
- Avoid collecting page content, cookies, credentials, or personal data unless essential and explicitly authorized.
- Use namespaced storage keys and validate stored values.
- Wait for DOM readiness when the target elements are not available at \`document-start\`.
- Make injected UI keyboard accessible and compatible with dark mode, zoom, and reduced motion.
- Use touch targets around 44 CSS px where feasible; use at least WCAG 2.2 AA target-size alternatives.
- Use safe-area insets and dynamic viewport units where needed.
- Document the exact userscript manager and its current installation workflow; verify it before giving app-store steps.

## Termux

- Use Termux only on supported Android devices, not iOS.
- Prefer packages from the official Termux repositories and current package manager.
- Avoid \`pip --break-system-packages\`; use a virtual environment for Python projects.
- Avoid global npm installs unless needed; prefer project-local tools or \`npx\` with pinned versions.
- Use environment variables or protected local files for secrets; never commit \`.env\`.
- Set timeouts, bounded retries, storage limits, and battery-aware scheduling.
- Termux:Boot and background execution require explicit user setup and Android battery/background permission checks.
- Do not claim an agent is offline-capable unless its model and required data are actually local.

## Mobile UX baseline

- Responsive layouts; no hover-only interactions.
- Minimum 16px form text to avoid iOS Safari focus zoom.
- Touch targets approximately 44×44 CSS px.
- Respect safe areas, dynamic viewport, text scaling, dark mode, and reduced motion.
- Keep primary actions reachable without blocking browser chrome.
- Preserve work during tab suspension, navigation, and network loss.
- Provide clear loading, offline, retry, and failure states.

## Verification

For each mobile deliverable, verify:
- supported OS/device and browser versions;
- install/build process;
- permissions and network behavior;
- keyboard, screen reader, contrast, zoom, and touch behavior;
- offline/interrupted-session behavior;
- signed artifact and dependency provenance;
- real-device smoke test, not just emulator success.

Do not hard-code a model name, token ceiling, or step count for every mobile task. Choose model and budget from the task's risk, latency, context, provider availability, and user-approved cost.
