import requests
import json

BASE = "http://localhost:8000"

# Register
reg = requests.post(f"{BASE}/api/v1/auth/register", json={
    "email": f"test{int(__import__('time').time())}@example.com",
    "display_name": "test",
    "password": "password123"
})
print(f"Register: {reg.status_code}")
user = reg.json()
print(f"User: {user}")

# Login
login = requests.post(f"{BASE}/api/v1/auth/login", data={
    "username": user["email"],
    "password": "password123"
})
print(f"Login: {login.status_code}")
token = login.json()["access_token"]
print(f"Token: {token[:20]}...")

# Create project
proj = requests.post(f"{BASE}/api/v1/projects", 
    json={"name": "Test", "key": "TST", "description": "test"},
    headers={"Authorization": f"Bearer {token}"}
)
print(f"Project: {proj.status_code}")
project = proj.json()
project_id = project["project_id"]
print(f"Project ID: {project_id}")

# Get board (this should cache)
board1 = requests.get(f"{BASE}/api/v1/projects/{project_id}/board",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"Board (1st call): {board1.status_code}")

# Get board again (should be cached)
board2 = requests.get(f"{BASE}/api/v1/projects/{project_id}/board",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"Board (2nd call): {board2.status_code}")

# Check Redis
import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
print(f"\nRedis board key: {r.get(f'board:{project_id}')[:100]}...")
print(f"Redis TTL: {r.ttl(f'board:{project_id}')}s")