# Canvas Workflow View — Design Document

Issue: #408

## Phase 1 (Current Implementation)

Read-only split-panel view at `#/workflow` with workflow execution support.

### Features
- **Workflow list panel**: Table of available workflows (name, step count, scope, description)
- **Detail panel**: Selected workflow's steps, Mermaid DAG visualization, Run button
- **Execution**: `POST /api/workflow/run/{name}` triggers async background execution; Canvas sends steps directly to target agents with `sender_id=canvas-workflow`
- **Wait mode polling**: Steps with `response_mode: wait` poll the target agent's task endpoint until the task reaches a terminal state (completed/failed), with a 10-minute timeout per step
- **409 retry**: If the target agent returns HTTP 409 (busy), the runner retries the send with a brief interval before reporting failure
- **Real-time progress**: SSE `workflow_update` events update step status icons
- **Persistent execution history**: Active runs cached in memory, completed runs persisted to SQLite (`.synapse/workflow_runs.db`). History survives server restarts. `get_runs`/`get_run` fall back to DB when runs are not in memory cache

### API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/workflow` | GET | List all workflows with steps |
| `/api/workflow/{name}` | GET | Single workflow detail |
| `/api/workflow/run/{name}` | POST | Start execution |
| `/api/workflow/runs` | GET | List active/recent runs |
| `/api/workflow/runs/{run_id}` | GET | Individual run status |

---

## Phase 2

### 2a. Persistent Execution History ✓ (Implemented)

Workflow runs are persisted in SQLite via `WorkflowRunDB` (`synapse/workflow_db.py`).

- Database: `.synapse/workflow_runs.db`
- Tables: `runs` (run_id, workflow_name, status, started_at, completed_at) + `run_steps` (run_id, step_index, target, message, status, started_at, completed_at, output, error)
- Active runs are cached in memory; completed runs are persisted to SQLite
- `get_runs` / `get_run` fall back to DB when a run is not in the in-memory cache
- API responses are unchanged (backward compatible)
- Benefits: history survives server restart, queryable, exportable

### 2b. Workflow CRUD via Canvas UI

Allow creating and editing workflows directly from the browser.

- **Create**: Form-based step builder with agent auto-complete from running agents
- **Edit**: Inline editing of existing YAML (or structured form)
- **Delete**: Confirmation dialog
- **Import/Export**: Upload/download YAML files
- API: `POST /api/workflow`, `PUT /api/workflow/{name}`, `DELETE /api/workflow/{name}`

### 2c. Conditional Branching and Parallel Steps

Extend workflow YAML format to support non-linear flows.

```yaml
steps:
  - id: review
    target: claude
    message: "Review changes"
    response_mode: wait
  - id: test
    target: gemini
    message: "Run tests"
    depends_on: [review]  # explicit dependency
  - id: lint
    target: codex
    message: "Run linters"
    depends_on: [review]  # parallel with test
  - id: deploy
    target: claude
    message: "Deploy if all green"
    depends_on: [test, lint]  # fan-in
    condition: "all_success"  # only if both passed
```

- `depends_on`: DAG-based execution (replaces sequential assumption)
- `condition`: `all_success`, `any_success`, `always` for conditional execution
- Mermaid DAG auto-generated from `depends_on` edges

### 2d. Workflow Templates

Pre-built workflow templates for common patterns:

- `post-impl`: docs + simplify + release
- `review-cycle`: review + test + fix
- `deploy-pipeline`: build + test + staging + production
- `onboarding`: bootstrap + context-share + first-task

Template gallery in Canvas UI with one-click instantiation.

### 2e. Webhook/Trigger Integration

Auto-trigger workflows based on events:

- Git push → run CI workflow
- Task board state change → run notification workflow
- Scheduled (cron-like) execution
- `trigger` field in YAML already exists (unused) for natural-language matching
