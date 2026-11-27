# Edge and CDN reference

## Cache policy
- Hashed static assets: long-lived immutable caching.
- Public HTML: short shared-cache TTL with revalidation where appropriate.
- Authenticated or personalized responses: private/no-store by default.
- APIs: cache only when response identity and invalidation are explicit.

## Edge compute
Edge execution helps only when it reduces distance to the data or avoids origin work. Several sequential calls to a distant database can make an edge function slower than a regional origin.

## Transport
- Enable HTTP/3 where supported and beneficial; it improves transport behavior, not application logic.
- Use 103 Early Hints/preload selectively for known critical resources.
- Do not rely on HTTP/2 Server Push.

## Safety checklist
- Check cookies, Authorization, Set-Cookie, tenant identity, and cache key.
- Never cache user-specific content in a shared cache.
- Do not cache errors or partially authorized responses.
- Test cache HIT/MISS behavior and purge/invalidation.
- Prefer standard CDN cache configuration over custom Worker code.
