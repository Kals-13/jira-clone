# Architecture Decision Records (ADRs)

## ADR-001: Optimistic Locking for Concurrency

**Decision**: Use optimistic locking (version field) instead of pessimistic locking

**Context**: Supporting 500+ concurrent users with high issue update rate

**Trade-offs**:
| Aspect | Optimistic | Pessimistic |
|--------|-----------|-------------|
| Throughput | High (no locks blocking reads) | Lower (locks serialize access) |
| Latency | Usually fast, higher on conflicts | Consistent but slower |
| Scalability | Supports 500+ users | Bottleneck at ~100 users |
| Conflict handling | Client retries (acceptable) | Automatic (transparent) |

**Rationale**: Board refresh on conflict is acceptable UX; prevents bottleneck

**Implementation**: Every `Issue` has `version: int`. PATCH must include current version.

---

## ADR-002: Event-Driven Architecture

**Decision**: Domain events (IssueCreated, StatusChanged) drive side effects

**Context**: Need real-time WS broadcasts, notifications, and audit logs without tight coupling

**Pattern**:
```
Service mutates DB → Emits DomainEvent → EventDispatcher routes to:
  ├─ WebSocket broadcast
  ├─ Notification queue (circuit-breaker protected)
  └─ Activity log
```

**Benefits**:
- ✅ Notifications can fail without blocking mutations
- ✅ Audit trail independent of delivery mechanism
- ✅ Easy to add new event handlers (webhooks, analytics)

**Cost**: Event replay buffer limited to 500 events (in-memory deque); multi-server needs Redis pub/sub

---

## ADR-003: CQRS for Board Queries

**Decision**: Separate `BoardReadModel` class for board read queries

**Context**: Board query is complex (4 queries total); caching needs to be transparent

**Implementation**:
- Write side: `IssueService` mutates Issue
- Read side: `BoardReadModel.get_board()` loads columns, sprint, issues
- Cache: Redis stores full board JSON (invalidated on mutations)

**Benefits**:
- ✅ Board read path isolated for optimization
- ✅ Cache layer only touches read model
- ✅ Write model unchanged

---

## ADR-004: Typed Error Hierarchy

**Decision**: Domain layer defines error types; API layer converts to HTTP

**Context**: Need consistent error responses; clients need to detect error types programmatically

**Errors**:
```python
JiraLiteError (base)
├── NotFoundError (404)
├── ConflictError (409)
├── WorkflowError (422)
├── ForbiddenError (403)
└── ValidationError (400)
```

**Response Format**:
```json
{
  "error": "CONFLICT",
  "message": "...",
  "correlation_id": "..."
}
```

**Benefits**:
- ✅ Clients handle errors by type, not string matching
- ✅ Correlation IDs enable request tracing
- ✅ All endpoints return consistent format

---

## ADR-005: PostgreSQL Advisory Locks for Sprint Operations

**Decision**: Use `pg_advisory_xact_lock()` for sprint start/complete

**Context**: Sprint state transitions must be atomic; multiple users can start sprints simultaneously

**Implementation**:
```python
lock_key = abs(hash(sprint_id)) % (2**31)
await db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
```

**Why**: 
- ✅ Application-level locks (independent of row locks)
- ✅ Serializes requests for same sprint
- ✅ Released automatically on transaction end

---

## ADR-006: Idempotency via Redis

**Decision**: Cache responses keyed by Idempotency-Key header

**Context**: Network timeouts cause duplicate submissions; idempotent operations needed

**Implementation**:
- Client includes `Idempotency-Key: <uuid>`
- Redis caches response for 24h
- Duplicate request returns cached response

**Benefits**:
- ✅ Safe to retry any POST/PATCH
- ✅ No duplicate issues created
- ✅ Works across server restarts (Redis-backed)

---

## ADR-007: Circuit Breaker for Notifications

**Decision**: Protect notification service with circuit breaker pattern

**Context**: External notification service can fail; don't block mutations

**States**:
```
CLOSED (normal) → 5 failures → OPEN (skip calls) → timeout → HALF_OPEN (test) → CLOSED
```

**Benefits**:
- ✅ Mutations unblocked by notification failures
- ✅ Automatic recovery attempts
- ✅ Dead-letter queue for retry

---

## ADR-008: Correlation IDs for Request Tracing

**Decision**: Every request gets UUID correlation ID (from header or generated)

**Context**: Need to trace requests across logs for debugging

**Implementation**:
- Header: `X-Correlation-ID: <uuid>` (input or generated)
- Middleware: stores in `contextvars` (async-safe)
- Logger: includes correlation_id in every log
- Response: echo back in `X-Correlation-ID` header

**Benefits**:
- ✅ Full request trace across all logs
- ✅ Support team can grep by correlation_id

---

## ADR-009: Role-Based Access Control (RBAC) Per-Project

**Decision**: Roles (Admin, Lead, Member, Viewer) are per-project, not global

**Context**: Different projects have different team structures; need flexible permissions

**Roles**:
| Role | Can | Cannot |
|------|-----|---------|
| Admin | Everything (global, out of scope) | - |
| Project Lead | Create/delete project, manage members, complete sprints | - |
| Member | Create issues, comment, transition own work | Delete project |
| Viewer | Read-only access | Create/modify anything |

**Enforcement**: On sensitive endpoints, check membership + role

---

## ADR-010: Custom Fields with Type Schema

**Decision**: Typed schema per project + JSON on Issue

**Context**: Teams need project-specific fields (severity, component, etc.) with validation

**Implementation**:
- `ProjectCustomField(project_id, name, field_type, options)`
- `field_type`: text, number, dropdown, date
- `Issue.custom_fields`: JSON dict with runtime validation

**Benefits**:
- ✅ Type safety (dropdown values must be in schema)
- ✅ Audit trail of field definitions
- ✅ Projects can have different fields

---

## ADR-011: Async/Await for Concurrency

**Decision**: Use Python async/await with asyncio + asyncpg

**Context**: Support 500+ concurrent users with limited threads

**Benefits**:
- ✅ One event loop handles many concurrent requests
- ✅ I/O-bound operations don't block (DB, Redis, WS)
- ✅ Scales to production

**Trade-off**: Can't use blocking libraries (sync psycopg2); must use asyncpg

---

## ADR-012: Redis for Three Concerns

**Decision**: Single Redis for caching, idempotency, rate limits

**Context**: Simplify infrastructure; three concerns are independent

**Namespacing**:
```
board:{project_id}             ← board cache
idempotency:{key}              ← response cache
ratelimit:user:{user_id}       ← per-user bucket
ratelimit:ip:{ip_address}      ← per-IP bucket
```

**Scaling**: In multi-server deployments, upgrade to Redis cluster or separate instances

---

## Decision Matrix

| Decision | Tradeoff | When to Revisit |
|----------|----------|-----------------|
| Optimistic Locking | Retries on conflict | If conflict rate >10% |
| CQRS | Code duplication | If board query too complex |
| Circuit Breaker | Delayed recovery | If notifications critical to UX |
| Async/Await | Learning curve | If performance bottleneck elsewhere |
| Per-Project RBAC | Complex permission checks | If global roles needed |

---

## Future ADRs

- ADR-013: Event Sourcing (full replay capability)
- ADR-014: Read-Write Splitting (separate read replicas)
- ADR-015: Sharding Strategy (horizontal scaling beyond single DB)
- ADR-016: GraphQL vs REST (API design)
