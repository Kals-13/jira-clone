# Sample Test Scenarios with Real Request/Response Examples

Complete walkthrough of core features with actual HTTP requests and responses from Swagger UI.

---

## Scenario 1: Concurrent Issue Updates (Optimistic Locking)

### Feature Demonstrated
✅ Optimistic locking prevents lost updates  
✅ Concurrency control with version field  
✅ Conflict detection and retry mechanism  

### Setup
- Project: `Demo Project` (key: `PROJ`)
- Issue: `PROJ-1` "Implement JWT authentication"
- Users: Alice (`alice@example.com`) and Bob (`bob@example.com`)

---

### Step 1a: Alice Registers
```
POST /api/v1/auth/register

Request Body:
{
  "email": "alice@example.com",
  "display_name": "Alice",
  "password": "password123"
}
```
**Response**: ![201 Created status](https://snipboard.io/7c4JDT.jpg)  
**Note**: Save `user_id` for later steps

---

### Step 1b: Alice Logs In
```
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

Request Body:
username=alice@example.com&password=password123
```
**Response**: ![Show `200 OK` with `access_token` visible ](https://snipboard.io/pVivLy.jpg) 
**Instructions**: Copy token → use in Swagger's "Authorize" button at top right  
**Key Point**: All subsequent requests need this token in Authorization header

---

### Step 2a: Create Project
```
POST /api/v1/projects

Headers:
Authorization: Bearer {token_from_step_1b}

Request Body:
{
  "name": "Demo Project",
  "key": "PROJ",
  "description": "Testing optimistic locking and workflows"
}
```
**Response**: ![Show `201 Created` response  ](https://snipboard.io/VMaIrf.jpg)
**Save**: `project_id`

---

### Step 2b: Create Issue (PROJ-1)
```
POST /api/v1/projects/{project-id}/issues

Headers:
Authorization: Bearer {token_from_step_1b}

Request Body:
{
  "title": "Implement JWT authentication",
  "description": "Add JWT token-based authentication system with refresh tokens",
  "issue_type": "story",
  "priority": "medium",
  "story_points": 5,
  "status_id": "To Do"
}
```
**Screenshot**: ![Show `201 Created` with **`version: 1`** highlighted ](https://snipboard.io/ao3Ek9.jpg) 
**Save**: `issue_id`  
**Key Point**: Notice `version: 1` - this is the optimistic lock version

---

### Step 3: Both Users Fetch Issue
```
GET /api/v1/issues/{issue-id}

Headers:
Authorization: Bearer {token_from_step_1b}

```
**Screenshot**: ![Show **`version: 1`** in the response body](https://snipboard.io/WHGhkI.jpg)  
**Key Point**: Both Alice and Bob see `version: 1` - they both now have the same version in memory

---

### Step 4: Alice Updates Assignee ✅ Success
```
PATCH /api/v1/issues/{issue-id}

Headers:
Authorization: Bearer {alice_token}

Request Body:
{
  "assignee_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
  "version": 1
}
```
**Screenshot**: ![Show **`version: 2`** (incremented from 1!)](https://snipboard.io/Zo0nsL.jpg)  
**Key Point**: Alice used `version: 1` in the request, so it succeeded. Version is now `2`.

---

### Step 5: Bob Tries Update with Stale Version ❌ Conflict
```
PATCH /api/v1/issues/770e8400-e29b-41d4-a716-446655440003

Headers:
Authorization: Bearer {bob_token}

Request Body:
{
  "priority": "high",
  "version": 1
}
```
**Screenshot**: ![Show **`409 Conflict`** status code with error message ](https://snipboard.io/TaGbfY.jpg) 
**Key Point**: This is the critical feature! Bob used `version: 1` (the stale version he fetched earlier), but the current version is `2`. The update is rejected to prevent lost updates.

---

### Step 6: Bob Fetches Latest and Retries ✅ Success
```
PATCH /api/v1/issues/{issue-id}

Headers:
Authorization: Bearer {bob_token}

Request Body:
{
  "priority": "high",
  "version": 2
}
```
**Screenshot**: ![Show **`version: 3`** in successful response](https://snipboard.io/oy1Kz4.jpg)  
**Key Point**: Bob now uses `version: 2` (the correct one) and the update succeeds!

---

### Expected Outcome
✅ Optimistic locking prevents lost updates  
✅ Version 1 → 2 (Alice's change)  
✅ Version 2 → 3 (Bob's retry)  
✅ Final state: `assignee=Alice`, `priority=high` (both changes preserved)  
✅ 409 Conflict properly detected when version stale

---

## Scenario 2: Issue Workflow Transitions

### Feature Demonstrated
✅ Workflow state machine enforcement  
✅ Valid transitions validation  
✅ Invalid transition rejection with helpful error

### Setup
- Project workflow: `To Do` → `In Progress` → `In Review` → `Done`
- Issue: `PROJ-1` (from Scenario 1)

---

### Step 1: Attempt Invalid Transition ❌ Rejected
```
POST /api/v1/issues/{issue-id}/transitions

Headers:
Authorization: Bearer {token}

Request Body:
{
  "target_status_id": "Done"
}
```
**Screenshot**: ![Show **`422 Unprocessable Entity`** with error details](https://snipboard.io/sVzc9q.jpg)  
**Key Point**: Workflow rules enforced - can't skip intermediate steps!

---

### Step 2: Take Valid Transition ✅ Success
```
POST /api/v1/issues/{issue-id}/transitions

Headers:
Authorization: Bearer {token}

Request Body:
{
  "target_status_id": "In Progress"
}
```
**Screenshot**: ![Show **`200 OK`** with new status "In Progress"](https://snipboard.io/hfGtZH.jpg)  
**Key Point**: Valid transition accepted, version incremented to 4

---

## Scenario 3: Sprint Management with Carry-Over

### Feature Demonstrated
✅ Sprint lifecycle (planned → active → completed)  
✅ Selective carry-over of incomplete issues  
✅ Velocity tracking  
✅ Activity audit trail

### Setup
- Project: `Demo Project`
- Create Sprint 1, add 3 issues

---

### Step 1: Create Sprint
```
POST /api/v1/sprints

Headers:
Authorization: Bearer {token}

Request Body:
{
  "name": "Sprint 1",
  "project_id": "c346c899-0b11-45a7-8c3d-22e5e700e0bd",
  "start_date": "2026-06-10T00:00:00Z",
  "end_date": "2026-06-24T00:00:00Z"
}
```
**Screenshot**: ![Show **`201 Created`** with sprint_id](https://snipboard.io/FmEcbj.jpg)  
**Save**: `sprint_id`

---

### Step 2: Start Sprint
```
POST /api/v1/sprints/{sprint-id}/start

Headers:
Authorization: Bearer {token}
```
**Screenshot**: ![Show status changed to **`active`**](https://snipboard.io/HBFCih.jpg)

---

### Step 3: Create Issues in Sprint
Create 3 issues and assign to sprint (similar to Scenario 1, Step 2b):
- **Task 1**: 5 story points → Complete it → Mark as Done
- **Task 2**: 3 story points → Leave as To Do
- **Task 3**: 3 story points → Leave as In Progress

(Details omitted for brevity - same pattern as PROJ-1 creation)

---

### Step 4: Complete Sprint with Selective Carry-Over
```
POST /api/v1/sprints/{sprint-id}/complete

Headers:
Authorization: Bearer {token}

Request Body:
{
  "target_sprint_id": "ae527b2d-d241-421d-b30e-2ba3b472c2ff",
  "selective_issue_ids": [
    "452333ff-b7de-47a6-818b-a4aef920b7ba", "c547dd70-407f-4bfb-821b-c13ccabdff4d"
  ]
}
```
**Screenshot**: ![j](https://snipboard.io/yDtZ41.jpg) 
**Key Point**: Only Task 1 (5 pts, Done) counts toward velocity. Tasks 2 & 3 are carried over.

---

## Scenario 4: Comments and Mentions

### Feature Demonstrated
✅ Adding comments to issues  
✅ @mention parsing  
✅ Activity trail

---

### Step 1: Add Comment with Mention
```
POST /api/v1/issues/{issue-id}/comments

Headers:
Authorization: Bearer {token}

Request Body:
{
  "body": "@Alice can you review this implementation?"
}
```
**Screenshot**: ![Show **`201 Created`** with comment body](https://snipboard.io/92J7bm.jpg)

---

## Scenario 5: Search Functionality

### Feature Demonstrated
✅ Full-text search  
✅ Pagination with cursor

---

### Step 1: Search Issues
```
GET /api/v1/search?project_id={project-id}&q=task&limit=10

Headers:
Authorization: Bearer {token}

Response: 200 OK
{
  "results": [
    {
      "id": "c547dd70-407f-4bfb-821b-c13ccabdff4d",
      "issue_key": "PROJ-931",
      "title": "Task 3",
      "type": "story",
      "status_id": "04d619eb-bbf7-44b9-bcd7-78468780671e",
      "assignee_id": null,
      "priority": "medium",
      "created_at": "2026-06-10T13:00:28.713789"
    },
    {
      "id": "452333ff-b7de-47a6-818b-a4aef920b7ba",
      "issue_key": "PROJ-206",
      "title": "Task 2",
      "type": "story",
      "status_id": "bf7f1a67-e479-4ecb-939c-4d14ee941f78",
      "assignee_id": null,
      "priority": "medium",
      "created_at": "2026-06-10T12:59:48.390416"
    },
    {
      "id": "0167376e-c2b4-43d1-a260-153a9c62f0c6",
      "issue_key": "PROJ-800",
      "title": "Task 1",
      "type": "story",
      "status_id": "d8626a6b-6958-498a-ad5d-c8ac774d258c",
      "assignee_id": null,
      "priority": "medium",
      "created_at": "2026-06-10T12:59:28.286525"
    }
  ],
  "next_cursor": null,
  "count": 3
}
```
**Screenshot**: ![Show search result with matched fields highlighted](https://snipboard.io/SO08xE.jpg)

---

## Scenario 6: Activity Feed (Audit Trail)

### Feature Demonstrated
✅ All mutations recorded  
✅ Audit trail for compliance

---

### Get Activity Feed
```
GET /api/v1/projects/{project-id}/activity?limit=20

Headers:
Authorization: Bearer {token}

Response: 200 OK
{
  "project_id": "c346c899-0b11-45a7-8c3d-22e5e700e0bd",
  "logs": [
    {
      "id": "be4ca1f7-b4a4-49b7-a8f2-2935171001d2",
      "issue_id": "c547dd70-407f-4bfb-821b-c13ccabdff4d",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "sprint_carry_over",
      "payload": {
        "from_sprint_id": "00391527-d5ef-4562-8e0f-25f67189ef42",
        "to_sprint_id": "ae527b2d-d241-421d-b30e-2ba3b472c2ff"
      },
      "timestamp": "2026-06-10T13:06:58.953284"
    },
    {
      "id": "d538e6e4-4745-4971-a900-5fe23fe6feb7",
      "issue_id": "452333ff-b7de-47a6-818b-a4aef920b7ba",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "sprint_carry_over",
      "payload": {
        "from_sprint_id": "00391527-d5ef-4562-8e0f-25f67189ef42",
        "to_sprint_id": "ae527b2d-d241-421d-b30e-2ba3b472c2ff"
      },
      "timestamp": "2026-06-10T13:06:58.953273"
    },
    {
      "id": "1b80cee6-8ee3-497e-878d-067599110140",
      "issue_id": "0167376e-c2b4-43d1-a260-153a9c62f0c6",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "status_changed",
      "payload": {
        "from": "7cb55148-c63a-4d1f-9ec1-2cf21d8fd7b1",
        "to": "d8626a6b-6958-498a-ad5d-c8ac774d258c",
        "auto_assigned": false,
        "reviewer_id": "723a4191-e065-4f06-a0d5-3ca7d0977267"
      },
      "timestamp": "2026-06-10T13:01:27.285829"
    },
    {
      "id": "7c39645e-801d-4813-8599-a8f07cf2f530",
      "issue_id": "0167376e-c2b4-43d1-a260-153a9c62f0c6",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "status_changed",
      "payload": {
        "from": "04d619eb-bbf7-44b9-bcd7-78468780671e",
        "to": "7cb55148-c63a-4d1f-9ec1-2cf21d8fd7b1",
        "auto_assigned": true,
        "reviewer_id": "723a4191-e065-4f06-a0d5-3ca7d0977267"
      },
      "timestamp": "2026-06-10T13:01:21.014069"
    },
    {
      "id": "572ab858-6a75-409b-ab58-3fd7e3f427c0",
      "issue_id": "0167376e-c2b4-43d1-a260-153a9c62f0c6",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "status_changed",
      "payload": {
        "from": "bf7f1a67-e479-4ecb-939c-4d14ee941f78",
        "to": "04d619eb-bbf7-44b9-bcd7-78468780671e",
        "auto_assigned": false,
        "reviewer_id": null
      },
      "timestamp": "2026-06-10T13:01:13.266820"
    },
    {
      "id": "83755958-73ba-4ac1-8d75-c787cb492bc2",
      "issue_id": "c547dd70-407f-4bfb-821b-c13ccabdff4d",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "issue_created",
      "payload": {
        "type": "story",
        "parent_id": null
      },
      "timestamp": "2026-06-10T13:00:28.728361"
    },
    {
      "id": "37811388-93e3-462a-85ad-3a2b1199127b",
      "issue_id": "452333ff-b7de-47a6-818b-a4aef920b7ba",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "issue_created",
      "payload": {
        "type": "story",
        "parent_id": null
      },
      "timestamp": "2026-06-10T12:59:48.403675"
    },
    {
      "id": "e01215fa-bf0f-4508-a23f-8e95d1271025",
      "issue_id": "0167376e-c2b4-43d1-a260-153a9c62f0c6",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "issue_created",
      "payload": {
        "type": "story",
        "parent_id": null
      },
      "timestamp": "2026-06-10T12:59:28.308755"
    },
    {
      "id": "e5a5e947-1438-44d3-a2ff-f64a77c59e93",
      "issue_id": "49bb9f74-8e93-49e1-950d-aa1fd80d2be5",
      "actor_id": "953c0eb0-b8c3-4329-958c-2aa0b40d066c",
      "event_type": "status_changed",
      "payload": {
        "from": "bf7f1a67-e479-4ecb-939c-4d14ee941f78",
        "to": "04d619eb-bbf7-44b9-bcd7-78468780671e",
        "auto_assigned": false,
        "reviewer_id": null
      },
      "timestamp": "2026-06-10T12:53:20.374770"
    },
    {
      "id": "ad026d00-2eb8-40c2-aa63-d6e565e872a4",
      "issue_id": "49bb9f74-8e93-49e1-950d-aa1fd80d2be5",
      "actor_id": "953c0eb0-b8c3-4329-958c-2aa0b40d066c",
      "event_type": "issue_updated",
      "payload": {
        "changes": {
          "priority": {
            "from": "IssuePriority.medium",
            "to": "high"
          }
        }
      },
      "timestamp": "2026-06-10T12:48:23.063149"
    },
    {
      "id": "76602529-1f2a-44a9-b001-03bc1b9240d9",
      "issue_id": "49bb9f74-8e93-49e1-950d-aa1fd80d2be5",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "issue_updated",
      "payload": {
        "changes": {
          "assignee_id": {
            "from": "None",
            "to": "723a4191-e065-4f06-a0d5-3ca7d0977267"
          }
        }
      },
      "timestamp": "2026-06-10T12:45:07.665071"
    },
    {
      "id": "02dc7f1c-ac4f-4fa0-92fe-7346c986f6ec",
      "issue_id": "49bb9f74-8e93-49e1-950d-aa1fd80d2be5",
      "actor_id": "723a4191-e065-4f06-a0d5-3ca7d0977267",
      "event_type": "issue_created",
      "payload": {
        "type": "story",
        "parent_id": null
      },
      "timestamp": "2026-06-10T12:39:30.562697"
    }
  ],
  "next_cursor": null
}
```

---

## Test Checklist

- Scenario 1, Step 5: Saw 409 Conflict when using stale version
- Scenario 1, Step 6: Successful retry after fetching latest version
- Scenario 2, Step 2: Saw 422 when attempting invalid transition
- Scenario 2, Step 3: Valid transition succeeded with status change
- Scenario 3, Step 4: Velocity recorded correctly (5 points)
- Scenario 3, Step 4: Carry-over count accurate (2 issues)
- Scenario 4, Step 1: Comment with mention created
- Scenario 5, Step 1: Search returned matching issues
- Scenario 6, Step 1: Activity feed shows all events

---