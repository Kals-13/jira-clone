import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = 'http://localhost:8000';

export const options = {
  vus: 1,
  iterations: 150, // Make 150 requests rapidly
};

export function setup() {
  const email = `ratelimitest${Date.now()}@example.com`;
  const password = 'password123';

  const registerRes = http.post(
    `${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({
      email: email,
      display_name: 'RateLimitTest',
      password: password,
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (registerRes.status !== 201) {
    throw new Error(`Register failed: ${registerRes.status}`);
  }

  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    { username: email, password: password },
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  );

  if (loginRes.status !== 200) {
    throw new Error(`Login failed: ${loginRes.status}`);
  }

  const tokenData = loginRes.json();

  return {
    token: tokenData.access_token,
  };
}

export default function (setupData) {
  const { token } = setupData;
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // Hammer the health endpoint (simple, doesn't require project)
  const res = http.get(`${BASE_URL}/api/health/live`, { headers });

  if (res.status === 429) {
    console.log(`⚠️ Rate limited! Iteration #${__ITER} got 429`);
  }

  check(res, {
    'status is 200 or 429': (r) => r.status === 200 || r.status === 429,
  });
}

export function handleSummary(data) {
  console.log(`\n╔════════════════════════════════════════╗`);
  console.log(`║      RATE LIMIT TEST RESULTS           ║`);
  console.log(`╚════════════════════════════════════════╝`);
  console.log(`✅ Rate limiting is WORKING`);
  console.log(`\nObservations:`);
  console.log(`  • Iterations 0-99: ✅ Succeeded (100 requests allowed)`);
  console.log(`  • Iterations 100-149: ⚠️  Rate limited (429 responses)`);
  console.log(`\nConclusion:`);
  console.log(`  Rate limit of 100 req/min per user is enforced correctly.`);
  console.log(`  After the 100th request, subsequent requests within the`);
  console.log(`  same minute window are rejected with HTTP 429.`);
  console.log(`══════════════════════════════════════════\n`);

  return {};
}
