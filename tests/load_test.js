import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = 'http://localhost:8000';

export const options = {
  stages: [
    { duration: '10s', target: 20 },
    { duration: '30s', target: 100 },
    { duration: '60s', target: 100 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.1'],
  },
};

export function setup() {
  const email = `loadtest${Date.now()}@example.com`;
  const displayName = `LoadTest${Date.now()}`;
  const password = 'password123';

  const registerRes = http.post(
    `${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({
      email: email,
      display_name: displayName,
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

  const projectRes = http.post(
    `${BASE_URL}/api/v1/projects`,
    JSON.stringify({
      name: 'Load Test Project',
      key: `LTST`,
      description: 'Project for load testing',
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${tokenData.access_token}`,
      },
    }
  );

  if (projectRes.status !== 201) {
    throw new Error(`Project creation failed: ${projectRes.status}`);
  }

  const projectData = projectRes.json();

  for (let i = 0; i < 10; i++) {
    http.post(
      `${BASE_URL}/api/v1/projects/${projectData.project_id}/issues`,
      JSON.stringify({
        title: `Load Test Issue ${i}`,
        description: `Test issue`,
        issue_type: 'story',
        status_id: 'To Do',
        story_points: 3,
        priority: 'medium',
      }),
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${tokenData.access_token}`,
        },
      }
    );
  }

  return {
    token: tokenData.access_token,
    projectId: projectData.project_id,
  };
}

export default function (setupData) {
  const { token, projectId } = setupData;
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  http.get(`${BASE_URL}/api/health/live`);
  sleep(1);

  const boardRes = http.get(`${BASE_URL}/api/v1/projects/${projectId}/board`, { headers });
  check(boardRes, {
    'board loads': (r) => r.status === 200,
    'has columns': (r) => r.json().columns && r.json().columns.length > 0,
    'under 500ms': (r) => r.timings.duration < 500,
  });

  sleep(1);
}
