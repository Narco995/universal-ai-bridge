# Backend and data performance reference

## Query design
- Index equality filters and sort/range columns based on real query patterns.
- Inspect actual plans and row estimates before adding indexes.
- Account for write amplification and storage cost.
- Prefer keyset pagination for large ordered datasets where stable cursors are possible.

## N+1 and batching
- Count database round trips.
- Batch related reads or use joins where appropriate.
- Verify ORM-generated SQL.

## Connection pools
- Size pools from measured concurrency, database limits, and workload.
- Include every application instance in the connection budget.
- Check transaction-pooling compatibility before using session state.

## Queues
- Make jobs idempotent.
- Use bounded retries with backoff and jitter.
- Provide dead-letter handling and visibility into queue age.
- Use an outbox when database state and job publication must be atomic.

## Cache and locks
- Cache only when freshness, privacy, and invalidation are understood.
- Prevent stampedes with bounded single-flight behavior.
- Use ownership tokens and atomic release for distributed locks.
- Use fencing tokens where stale workers can write after lease expiry.
