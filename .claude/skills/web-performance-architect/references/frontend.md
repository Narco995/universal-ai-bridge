# Frontend performance reference

## LCP
- Identify the real LCP element in a browser trace.
- Do not lazy-load the LCP resource.
- Set \`fetchpriority="high"\` only when evidence shows the resource is the LCP candidate.
- Keep critical CSS and font requests small; avoid indiscriminate preloads.

## CLS
- Give images, videos, iframes, and embeds stable dimensions or aspect ratios.
- Reserve space for dynamic content.
- Use font metric overrides only after measuring fallback/swap layout changes.
- Avoid inserting content above the user's current reading position.

## INP
- Profile long tasks and event handlers.
- Split expensive work and yield to the browser.
- Defer nonessential scripts.
- Use passive listeners for scroll/touch when the handler does not call preventDefault.
- Use transitions for non-urgent UI updates where supported by the framework.

## Images and bundles
- Use responsive sources with \`srcset\` and \`sizes\`.
- Use AVIF/WebP with sensible fallbacks where supported.
- Lazy-load below-the-fold media.
- Analyze bundle composition before changing dependencies.
- Split by route and defer heavy charts/editors until needed.

A static audit cannot determine actual LCP, INP, or CLS. Verify in a browser and with field data.
