---
name: web-performance-architect
description: |
  Performance-first web and API architecture covering Core Web Vitals,
  rendering, resource loading, images, bundles, backend queries, caching,
  queues, CDNs, and measurement. Use for web builds, audits, and optimization.
---

# Web Performance Architect

## Core rule: measure before optimizing

Separate:
- lab measurements (Lighthouse, browser traces, synthetic tests);
- field measurements (CrUX or consent-aware Real User Monitoring);
- backend measurements (traces, query plans, saturation, queue age).

Use Google's current "good" Core Web Vitals thresholds as field targets: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile. Tighter internal budgets are goals, not guarantees. Do not claim a site meets them without representative field evidence.

## Workflow

1. Classify frontend, backend, database, network, CDN, and infrastructure scope.
2. Capture a reproducible baseline.
3. Identify the measured bottleneck.
4. Choose the smallest effective change.
5. Test correctness, privacy, and regressions.
6. Compare before/after using the same device, network, route, and workload.
7. Report uncertainty and remaining bottlenecks.

## Rendering and frontend

Choose static generation, server rendering, streaming, or client rendering based on freshness, personalization, SEO, and interaction requirements. Prefer the least client JavaScript that meets the product needs.

- Reserve media and embed dimensions to prevent layout shift.
- Prioritize only the actual LCP resource.
- Lazy-load below-the-fold images and embeds.
- Use responsive image formats and \`srcset\`/\`sizes\`.
- Use route-level code splitting and inspect bundle composition before removing dependencies.
- Avoid long main-thread tasks; yield or offload CPU-heavy work.
- Defer nonessential third-party scripts.
- Respect reduced motion and accessibility.
- Use Speculation Rules only for safe navigations without side effects or per-view accounting.

Static HTML checks are heuristics. The first image in source order is not necessarily the LCP element; inspect the browser trace.

## Backend and data

- Measure query count, round trips, execution plans, pool wait, and lock contention.
- Avoid N+1 queries with joins or batching.
- Use keyset pagination for large ordered datasets where appropriate.
- Add indexes based on actual query plans and write costs.
- Pool connections based on measured concurrency and database limits.
- Use queues for slow or nonessential work; make jobs idempotent.
- Use an outbox pattern when a database transaction must reliably publish work.
- Prefer the simplest datastore that meets workload and recovery requirements.

Do not add Redis, PostgreSQL, or an edge database merely because they are popular. SQLite WAL is suitable for many single-host workloads; it is not a multi-host shared database on a network filesystem.

## Cache safety

Before caching, establish:
- whether the response is public or user-specific;
- which headers/cookies/authentication affect the representation;
- whether \`Set-Cookie\` is present;
- freshness and invalidation requirements;
- whether stale data is safe;
- cache-key normalization and tenant isolation.

Never place authenticated or personalized responses in a shared cache unless the cache key and isolation rules are explicitly proven safe. Default private responses to \`Cache-Control: private, no-store\` where appropriate.

Prefer standard \`Cache-Control\`, \`ETag\`, and CDN features over custom edge cache code. Custom cache workers must reject or bypass requests with authorization/cookies unless explicitly designed for safe public caching, avoid caching \`Set-Cookie\`, handle cache errors, and prevent cache stampedes.

## Distributed locks

A Redis lock must have:
- a unique random ownership token;
- a bounded lease;
- atomic compare-and-delete release (Lua or equivalent);
- safe behavior if the lease expires while work continues;
- fencing tokens where stale owners could overwrite newer work.

Never use an unconditional \`DEL lock:key\` in \`finally\`: it may delete a lock acquired by a different worker after the original lease expired.

## Protocol selection

- REST over HTTP for broad public APIs and cacheable reads.
- SSE for server-to-client event streams when one-way updates suffice.
- WebSockets for genuinely bidirectional low-latency sessions.
- gRPC for typed service-to-service communication where the operational complexity is justified.
- MCP for model-to-tool interaction; it is not a replacement for ordinary application APIs.

## Performance budgets

Set route-specific budgets based on the product and target devices. Example starting budgets:
- LCP internal goal: 1.5–2.0 s on a representative mid-tier mobile profile;
- INP internal goal: 150 ms;
- CLS internal goal: 0.05;
- first-load JavaScript: set from measured product needs rather than a universal 100 KB rule.

Budgets are guardrails, not universal standards. Record gzip/brotli size and test the actual deployed build.

## Verification

- HTML heuristic audit for markup issues.
- Lighthouse CI and browser performance traces for lab measurements.
- CrUX or consent-aware RUM for field data.
- \`EXPLAIN (ANALYZE, BUFFERS)\` for PostgreSQL query investigation.
- Application traces and metrics for end-to-end latency.
- Load tests with realistic concurrency and data distribution.

Every recommendation must state the expected bottleneck, measurement, trade-off, and rollback.
