# Load Testing with k6

## Prerequisites

1. **k6 installed**: https://k6.io/docs/get-started/installation/
   ```bash
   # macOS
   brew install k6

   # or download from https://github.com/grafana/k6/releases
   ```

2. **Application running**:
   ```bash
   docker-compose up -d postgres redis
   # Then in another terminal:
   uvicorn app.main:app --reload
   ```

## Running the Load Test

### Basic run (100 concurrent users for ~100 seconds):
```bash
k6 run tests/load_test.js
```

### With custom duration:
```bash
k6 run tests/load_test.js --duration 5m --vus 50
```

### With detailed output:
```bash
k6 run tests/load_test.js --vus 100 --duration 60s -v
```

## What the test does

1. **Setup phase** (once per test run):
   - Registers a new user
   - Logs in and gets an auth token
   - Creates a project
   - Populates it with 10 issues

2. **Load phase** (runs for each VU):
   - Each VU repeatedly:
     - Fetches `/api/health/live` (no auth)
     - Fetches `/api/v1/projects/{id}/board` (auth required) — **this tests cache hit rate**
     - Fetches `/api/metrics` (observability)
     - Sleeps 1-2 seconds between iterations

## Metrics to watch

| Metric | Target | Notes |
|--------|--------|-------|
| `http_req_duration` p95 | < 500ms | Board query should be fast with cache |
| `http_req_duration` p99 | < 1000ms | Tail latency |
| `http_req_failed` rate | < 1% | Error rate should stay low |
| `http_reqs` total | N/A | Total requests sent |
| `board_load_time_ms` p95 | < 500ms | Custom metric for board latency |

## Output interpretation

```
http_reqs...........: 5000 total, 50/s
http_req_duration...: avg=123ms, p(95)=234ms, p(99)=456ms
http_req_failed.....: 0.5%
```

✅ **Good**: p95 < 500ms, failures < 1%  
⚠️  **Concerning**: p95 > 1000ms or failures > 5%  
❌ **Critical**: Timeouts or failures > 10%

## Cache performance

With the Redis board cache enabled (30s TTL), you should see:

- **First 10 requests** to a board: slower (cache miss, DB hit)
- **Next 1000 requests** to the same board: faster by ~10–20x (cache hit)
- **After 30 seconds of no access**: cache expires, next request is slow again

To verify cache is working:

```bash
# In another terminal, watch Redis cache
redis-cli
> KEYS board:*
> TTL board:proj-xxx
```

## Stress testing

To find the breaking point:

```bash
k6 run tests/load_test.js \
  --stage 1m:100 \  # 1 min at 100 VUs
  --stage 1m:200 \  # 1 min at 200 VUs
  --stage 1m:500    # 1 min at 500 VUs
```

Stop when you see error rate spike or p99 exceed 5000ms.

## Troubleshooting

### "TypeError: Value is not an object: null"
- Make sure the application is running on `http://localhost:8000`
- Check that Docker containers are up: `docker-compose ps`

### "Failed to register user: 400"
- Make sure the database migrations ran
- Check PostgreSQL is running: `docker-compose logs postgres`

### "board loads successfully: 0/100 (0%)"
- Verify auth token is valid
- Check the API logs for 401/403 errors

### Cache not improving latency
- Verify Redis is running: `docker-compose ps redis`
- Check Redis connectivity: `redis-cli ping`
- Ensure `app/core/caching.py` is being imported by `read_models.py`
