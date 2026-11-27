---
name: claud-uiux-pro
description: |
  UX and frontend architecture for user-facing software: design systems,
  components, dashboards, forms, navigation, accessibility, responsive UI,
  and interaction design. Use when designing or reviewing an interface.
---

# UX Solution Architect

## Scope

Apply this skill to interfaces and user-facing artifacts. Do not force UI architecture rules onto ordinary factual answers or unrelated backend tasks.

## Design principles

1. Understand the user's goal and mental model before choosing components.
2. Prefer progressive disclosure over exposing every option at once.
3. Keep navigation and decision points understandable; group choices by task.
4. Design for keyboard, touch, screen readers, zoom, contrast, and reduced motion from the start.
5. Separate domain logic, data access, state, and presentation.
6. Use design tokens for color, spacing, typography, borders, and elevation.
7. Prefer the simplest component architecture that meets requirements; use compound components when they reduce coupling, not as a ritual.

## Stack selection

- Respect the existing repository and its current stack first.
- Do not migrate frameworks solely to use a newer version.
- For new React applications, use the currently supported stable React and TypeScript releases, with strict type checking.
- Prefer framework-native server rendering, loaders, or server components for server data when suitable.
- Use a client cache such as TanStack Query when client-side server-state synchronization is actually needed.
- Use local component state for local concerns; choose Context or a state library based on update frequency and scope.
- Use accessible headless primitives where they materially improve keyboard and interaction behavior.
- Use the existing CSS system or a tokenized utility framework; avoid introducing a second styling system without justification.

## Accessibility acceptance

Target WCAG 2.2 AA unless the product specifies a stricter requirement.

Check:
- semantic HTML and accessible names;
- complete keyboard operation and visible focus;
- focus order and focus not obscured;
- contrast and non-color status cues;
- labels, instructions, errors, and validation;
- target size and alternatives to dragging;
- accessible authentication, paste, and password managers;
- zoom/reflow and text resizing;
- screen-reader announcements for asynchronous changes;
- reduced motion and media alternatives.

Do not claim WCAG compliance from visual inspection alone. Use automated checks (for example axe) plus manual keyboard and assistive-technology review.

## Performance-aware UI

- Reserve dimensions for images, video, embeds, skeletons, and asynchronously inserted content.
- Load only the JavaScript needed for the current route and interaction.
- Avoid long main-thread tasks; yield or move expensive work off the main thread where appropriate.
- Defer nonessential third-party scripts.
- Avoid unnecessary global state and rerender fan-out.
- Measure LCP, INP, CLS, bundle size, and interaction traces on representative devices.
- Apply \`web-performance-architect\` for page delivery, backend, CDN, and caching decisions.

## Required design review

For substantial interfaces, provide:
1. User goal and primary workflow.
2. Information architecture and decision points.
3. Component and state boundaries.
4. Design token strategy.
5. Accessibility plan and tests.
6. Loading, empty, error, and offline states.
7. Performance budgets and measurement plan.
8. Trade-offs and unresolved assumptions.

## Anti-patterns

Avoid:
- arbitrary hard-coded visual values where tokens exist;
- inaccessible custom controls when native elements suffice;
- \`any\` where a safe type can be modeled;
- using effects for data fetching when the framework has a better data-loading primitive;
- global state for local state;
- loading every dashboard widget on first paint;
- hidden focus indicators;
- placeholder-only form labels;
- claiming performance or accessibility without evidence.
