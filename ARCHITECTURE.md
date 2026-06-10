# Architecture Decision Records & Design

## High-Level Architecture

## 1. Domain Layer

**Purpose**: Core business logic independent of infrastructure

**Components**:
- `Issue`, `Sprint`, `Project` models with relationships
- `WorkflowEngine` validates state transitions
- `IssueCreated`, `StatusChanged` domain events
- `NotFoundError`, `ConflictError`, `WorkflowError` typed exceptions

**Key Decision**: Events are immutable dataclasses, enabling audit trail and notifications without coupling to HTTP layer.

## 2. Application Layer

**Services**:
- `IssueService` — create/update issues, transitions
- `SprintService` — sprint lifecycle
- `CollaborationService` — comments, mentions, watchers

**Pattern**: Each service receives `dispatcher: EventDispatcher` to emit domain events after mutations. Decouples business logic from side effects (notifications, WS broadcasts).

## 3. API Layer

**Routes by Feature**:
- Auth: register, login, me
- Projects: CRUD, board view, custom fields
- Issues: get, update, transition, search
- Sprints: CRUD, start, complete, carry-over
- Comments: CRUD, watchers, mentions
- Activity: paginated audit log
- WebSocket: real-time board sync

**Middleware Stack** (innermost to outermost):
1. `CorrelationMiddleware` — inject request ID, log latency
2. `RateLimitMiddleware` — 100 req/min per user, 1000 per IP
3. `IdempotencyMiddleware` — deduplicate retries via Redis
4. `CORSMiddleware` — cross-origin requests

## 4. Infrastructure Layer

**Database** (`PostgreSQL`):
- Relational schema with foreign keys
- Indexes on high-cardinality lookups (project_id, status_id, created_at)
- Advisory locks for sprint mutations
- Optimistic locking via `version` column

**Cache** (`Redis`):
- Board queries (30s TTL)
- Idempotency responses (24h TTL)
- Rate limit buckets (60s TTL)

**Repositories**: Data access layer with query builders

## 5. Event System

```
Service emits event
    ↓
EventDispatcher routes by type
    ├→ WebSocket broadcast (async)
    ├→ Notification service (async, circuit-breaker protected)
    └→ Activity log (async)
```

**Why**: Decouples mutations from side effects, enables:
- Offline clients to catch up via replay
- Graceful degradation if notifications fail
- Audit trail independent of delivery

## Key Design Decisions

### 1. Optimistic Locking vs. Pessimistic Locking

**Decision**: Optimistic (version field on Issue)

**Why**:
- Reads don't block writes
- Supports 500+ concurrent users
- Client retries on conflict are user-acceptable (board auto-refreshes)

**Tradeoff**: More retries under high contention, vs. higher throughput

### 2. Event Sourcing vs. Audit Trail

**Decision**: Audit trail (ActivityLog table)

**Why**:
- Simpler to query for compliance (SELECT * FROM activity WHERE event_type = 'role_changed')
- No complex event replay logic
- Works with any schema evolution

**Tradeoff**: No full event replay; can't reconstruct exact state at time T

### 3. CQRS (Read Model Separation)

**Decision**: Separate `BoardReadModel` for board queries

**Why**:
- Board queries optimized for reads (4 total queries, no N+1)
- Cache layer only touches read model
- Write model (IssueService) unchanged

**Tradeoff**: Two code paths to maintain; sync between read/write

### 4. WebSocket Event Replay

**Decision**: In-memory deque (500-event buffer)

**Why**: Simple, 30-second typical buffer sufficient

**Tradeoff**: Multi-server deployments need Redis pub/sub (see SCALING.md)

### 5. Rate Limiting Strategy

**Decision**: Token-bucket in Redis per-user + per-IP

**Why**:
- Distributed (survives server restarts)
- Simple to tune (100 req/min = 1.67/sec allowance)
- Fail-open if Redis down


### 6. Custom Field Storage

**Decision**: Typed schema (ProjectCustomField) + JSON on Issue

**Why**:
- Schema per project (flexibility)
- Runtime validation (dropdown must be in options)
- Audit trail of field definitions

**Tradeoff**: Client must validate against schema

---

## Concurrency Model

### Issue Updates

```
Client A: PATCH /issues/123 (version: 1)
  ↓
Check: Issue.version == 1 ✓
  ↓
Update & increment: version = 2
  ↓
Emit StatusChanged event
  ↓
200 OK

Client B: PATCH /issues/123 (version: 1)
  ↓
Check: Issue.version == 1 ✗ (now 2)
  ↓
409 Conflict (Client retries)
```

### Sprint Operations

```
POST /sprints/{id}/start
  ↓
pg_advisory_xact_lock(hash(sprint_id))  ← Serializes concurrent requests
  ↓
Check: status == planned ✓
Check: no other active sprint ✓
  ↓
status = active
  ↓
COMMIT (lock released)
```

---

## Performance Optimizations

### N+1 Prevention
Board query:
```python
# 4 queries total:
SELECT * FROM workflow_statuses WHERE project_id = ?
SELECT * FROM sprints WHERE project_id = ? AND status = 'active'
SELECT * FROM issues WHERE project_id = ?
# (no per-issue queries)
```

### Caching Hierarchy
```
Request → Redis board cache (30s)
       ↓ miss
       → Load from DB (4 queries)
       ↓
       → Parse & store in Redis
       → Return to client
```

### Indexes
```sql
-- Issues
CREATE INDEX ix_issues_project_id ON issues(project_id);
CREATE INDEX ix_issues_sprint_id ON issues(sprint_id);
CREATE INDEX ix_issues_status_id ON issues(status_id);

-- Activity (for feeds)
CREATE INDEX ix_activity_project_created ON activity_logs(project_id, created_at DESC);
```

---

## Error Handling

**Typed Error Hierarchy**:
```
JiraLiteError (http_status, code, message)
├── NotFoundError (404, "NOT_FOUND")
├── ConflictError (409, "CONFLICT")
├── WorkflowError (422, "WORKFLOW_VIOLATION")
├── ForbiddenError (403, "FORBIDDEN")
└── ValidationError (400, "VALIDATION_ERROR")
```

**Response Format**:
```json
{
  "error": "CONFLICT",
  "message": "Version conflict. Expected 2, got 1.",
  "correlation_id": "req-uuid-..."
}
```

**Why**: Clients can:
- Detect error type by `error` code (no string parsing)
- Trace requests via correlation ID
- Retry idempotent ops automatically

---

## Security Posture

### Authentication
- JWT tokens (HS256, 60-min expiry)
- bcrypt password hashing (12 rounds)

### Authorization
- Row-level: users only see projects they're members of
- Role-based: admin/lead/member/viewer per project
- Endpoint checks enforce membership/role

### Data Protection
- No plaintext secrets in logs
- Correlation IDs for tracing
- Audit log for sensitive ops (role changes, deletions)

### Resilience
- Circuit breaker on notifications (fail-open)
- Rate limiting on all endpoints
- Connection pooling with health checks

---

## Deployment Considerations

### Stateless API
- No in-memory state
- Scale to N instances behind load balancer
- All state in PostgreSQL or Redis

### Monitoring & Observability
- Prometheus metrics on all endpoints
- Structured logs with correlation IDs
- Health checks: `/api/health/live` (alive) and `/api/health/ready` (dependencies)

---

## Future Improvements

1. **Event Sourcing** — Full replay for time-travel debugging
2. **Read Model Materialization** — Separate read DB optimized for complex queries
3. **Webhook Subscriptions** — Clients subscribe to issue events
4. **Bulk Operations** — Move 100 issues to sprint in one call
5. **Custom Workflow Conditions** — "Only lead can move to Done if assigned"
6. **Burndown Charts** — Sprint progress visualization
7. **Notification Channels** — Slack, email, Teams integrations
