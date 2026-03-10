# Architecture Patterns

**Domain:** Unified workflow consolidation for serverless deploy tool (Ferry v1.4)
**Researched:** 2026-03-10

## Recommended Architecture

**Option B: All dispatches target a single `ferry.yml`, per-type dispatch model preserved.**

The backend continues to send one `workflow_dispatch` per resource type. The only change is the target filename: all dispatches go to `ferry.yml` instead of `ferry-lambdas.yml` / `ferry-step_functions.yml` / `ferry-api_gateways.yml`. The unified workflow uses a shared setup job that exposes `resource_type` as an output, and conditional deploy jobs (`if: needs.setup.outputs.resource_type == 'lambda'`) route to the correct deploy steps.

This is the correct approach because it minimizes backend changes (one constant swap), preserves the proven per-type dispatch payload model, and keeps each workflow run focused on a single resource type -- meaning GHA logs stay clean and matrix fan-out works identically to today.

```
BEFORE (v1.3):
  Push (3 lambdas + 1 SF changed)
    -> Backend groups by type
    -> Dispatch 1: POST ferry-lambdas.yml        (payload: 3 lambda resources)
    -> Dispatch 2: POST ferry-step_functions.yml  (payload: 1 SF resource)

AFTER (v1.4):
  Push (3 lambdas + 1 SF changed)
    -> Backend groups by type
    -> Dispatch 1: POST ferry.yml  (payload: 3 lambda resources, resource_type=lambda)
    -> Dispatch 2: POST ferry.yml  (payload: 1 SF resource, resource_type=step_function)
```

Each dispatch still carries exactly one resource type. Two parallel runs of `ferry.yml` execute simultaneously (GHA allows this by default when no concurrency group is set).

### Component Boundaries

| Component | Responsibility | Changes for v1.4 |
|-----------|---------------|-------------------|
| `constants.py` (ferry-utils) | Maps ResourceType to workflow suffix | **MODIFY**: Remove `RESOURCE_TYPE_WORKFLOW_MAP` entirely, replace with single `WORKFLOW_FILENAME = "ferry.yml"` constant |
| `trigger.py` (ferry-backend) | Constructs workflow filename, POSTs dispatch | **MODIFY**: Use `WORKFLOW_FILENAME` instead of per-type lookup (delete 2 lines, add 1) |
| `parse_payload.py` (ferry-action) | Parses payload, builds GHA matrix | **MODIFY**: Add `resource_type` output alongside `matrix` |
| `setup/action.yml` (ferry-action) | Composite action wrapping parse_payload | **MODIFY**: Expose new `resource_type` output |
| `ferry.yml` (user workflow) | **NEW** unified workflow file | **NEW**: Single file with setup job + 3 conditional deploy jobs |
| `ferry-lambdas.yml` (user workflow) | Per-type Lambda workflow | **DELETE**: Replaced by ferry.yml |
| `ferry-step_functions.yml` (user workflow) | Per-type SF workflow | **DELETE**: Replaced by ferry.yml |
| `ferry-api_gateways.yml` (user workflow) | Per-type APGW workflow | **DELETE**: Replaced by ferry.yml |
| `docs/*.md` | Workflow setup documentation | **MODIFY**: Update all three docs to reference ferry.yml |

### Data Flow

**Current flow (v1.3):**
```
handler.py -> trigger_dispatches()
  -> groups affected by type
  -> for each type:
     -> RESOURCE_TYPE_WORKFLOW_MAP[type] -> "lambdas" / "step_functions" / "api_gateways"
     -> workflow_file = f"ferry-{workflow_name}.yml"
     -> POST /repos/{repo}/actions/workflows/{workflow_file}/dispatches
        body: {ref: "main", inputs: {payload: <DispatchPayload JSON>}}
```

**New flow (v1.4):**
```
handler.py -> trigger_dispatches()
  -> groups affected by type
  -> for each type:
     -> workflow_file = WORKFLOW_FILENAME  ("ferry.yml")
     -> POST /repos/{repo}/actions/workflows/{workflow_file}/dispatches
        body: {ref: "main", inputs: {payload: <DispatchPayload JSON>}}
```

**User workflow data flow (v1.4):**
```
workflow_dispatch triggers ferry.yml
  -> setup job:
     -> parse_payload.py reads INPUT_PAYLOAD
     -> outputs: matrix (JSON), resource_type (string)
  -> deploy-lambdas job:
     -> if: needs.setup.outputs.resource_type == 'lambda'
     -> matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
     -> steps: checkout -> build -> deploy
  -> deploy-stepfunctions job:
     -> if: needs.setup.outputs.resource_type == 'step_function'
     -> matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
     -> steps: checkout -> deploy-stepfunctions
  -> deploy-apigateways job:
     -> if: needs.setup.outputs.resource_type == 'api_gateway'
     -> matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
     -> steps: checkout -> deploy-apigw
```

Only one deploy job runs per workflow dispatch. The other two are skipped (reported as "Success" by GHA, which is correct for required status checks).

## Detailed Changes Per File

### 1. `utils/src/ferry_utils/constants.py` -- MODIFY

**Current:**
```python
RESOURCE_TYPE_WORKFLOW_MAP: dict[ResourceType, str] = {
    ResourceType.LAMBDA: "lambdas",
    ResourceType.STEP_FUNCTION: "step_functions",
    ResourceType.API_GATEWAY: "api_gateways",
}
```

**New:**
```python
# Single workflow file for all resource types (v1.4 unified workflow)
WORKFLOW_FILENAME = "ferry.yml"
```

Delete `RESOURCE_TYPE_WORKFLOW_MAP` entirely. The per-type workflow name mapping is no longer needed because all dispatches target the same file. Keep `ResourceType` enum (still used for grouping, payload model, and conditional routing).

### 2. `backend/src/ferry_backend/dispatch/trigger.py` -- MODIFY

**Current (lines 154-155):**
```python
workflow_name = RESOURCE_TYPE_WORKFLOW_MAP[ResourceType(rtype)]
workflow_file = f"ferry-{workflow_name}.yml"
```

**New:**
```python
workflow_file = WORKFLOW_FILENAME
```

Update imports: remove `RESOURCE_TYPE_WORKFLOW_MAP`, add `WORKFLOW_FILENAME`. The rest of the function is unchanged -- grouping, payload building, size check, POST, logging all stay the same.

### 3. `action/src/ferry_action/parse_payload.py` -- MODIFY

Add `resource_type` as a second output. The `main()` function currently writes only `matrix`. Add one line:

```python
set_output("resource_type", payload.resource_type)
```

The `build_matrix()` function is unchanged. The new `resource_type` output enables conditional job routing in the unified workflow.

Note: extract the `DispatchPayload` parse into a shared step so both `matrix` and `resource_type` come from the same parsed payload (they already do in `main()` -- just add the second `set_output` call).

### 4. `action/setup/action.yml` -- MODIFY

Add new output:

```yaml
outputs:
  matrix:
    description: "JSON string for fromJson() in GHA strategy matrix"
    value: ${{ steps.parse.outputs.matrix }}
  resource_type:
    description: "Resource type from dispatch payload (lambda, step_function, api_gateway)"
    value: ${{ steps.parse.outputs.resource_type }}
```

### 5. User workflow `ferry.yml` -- NEW

This is the file users create in `.github/workflows/ferry.yml`. It replaces three files with one. Structure:

```yaml
name: Ferry Deploy

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"
        required: true

permissions:
  id-token: write
  contents: read
  checks: write

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
      resource_type: ${{ steps.parse.outputs.resource_type }}
    steps:
      - uses: actions/checkout@v4
      - name: Parse Ferry payload
        id: parse
        uses: <ferry-repo>@<ref>/action/setup
        with:
          payload: ${{ inputs.payload }}

  deploy-lambdas:
    name: "deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Build container
        id: build
        uses: <ferry-repo>@<ref>/action/build
        with:
          resource-name: ${{ matrix.name }}
          source-dir: ${{ matrix.source }}
          ecr-repo: ${{ matrix.ecr }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          runtime: ${{ matrix.runtime }}
      - name: Deploy Lambda
        uses: <ferry-repo>@<ref>/action/deploy
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          image-uri: ${{ steps.build.outputs.image-uri }}
          image-digest: ${{ steps.build.outputs.image-digest }}
          deployment-tag: ${{ matrix.deployment_tag }}
          trigger-sha: ${{ matrix.trigger_sha }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}

  deploy-stepfunctions:
    name: "deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'step_function'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Deploy Step Functions
        uses: <ferry-repo>@<ref>/action/deploy-stepfunctions
        with:
          resource-name: ${{ matrix.name }}
          state-machine-name: ${{ matrix.state_machine_name }}
          definition-file: ${{ matrix.definition_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}

  deploy-apigateways:
    name: "deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'api_gateway'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Deploy API Gateway
        uses: <ferry-repo>@<ref>/action/deploy-apigw
        with:
          resource-name: ${{ matrix.name }}
          rest-api-id: ${{ matrix.rest_api_id }}
          stage-name: ${{ matrix.stage_name }}
          spec-file: ${{ matrix.spec_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}
```

Key design decisions in the workflow:
- **No concurrency group**: Multiple dispatches (one per type) run in parallel by default. This matches v1.3 behavior where separate workflow files ran in parallel.
- **`if` on deploy jobs, not on matrix**: The `if` condition gates the entire job. GHA skips the job (including matrix evaluation) when the condition is false, so `fromJson` on an unrelated matrix never executes.
- **Each deploy job has its own `name`**: `deploy ${{ matrix.name }}` gives clear GHA run names.
- **Skipped jobs report as "Success"**: GHA treats skipped jobs as successful, so required status checks work correctly.

## Patterns to Follow

### Pattern 1: Conditional Job Routing via Setup Output

**What:** The setup job parses the dispatch payload and exposes `resource_type` as a string output. Each deploy job uses `if: needs.setup.outputs.resource_type == '<type>'` to conditionally run.

**Why this over alternatives:**
- `if` on the job level prevents GHA from even evaluating the `matrix` expression for skipped jobs, avoiding `fromJson` errors on mismatched matrix shapes.
- The string comparison is simple and debuggable -- visible in GHA logs as "this job was skipped because the condition was not met."
- No changes to the dispatch payload model (`DispatchPayload` already carries `resource_type`).

**Example:**
```yaml
jobs:
  setup:
    outputs:
      resource_type: ${{ steps.parse.outputs.resource_type }}
      matrix: ${{ steps.parse.outputs.matrix }}

  deploy-lambdas:
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
```

### Pattern 2: Single Constant for Workflow Filename

**What:** Replace the `RESOURCE_TYPE_WORKFLOW_MAP` dictionary with a single `WORKFLOW_FILENAME` string constant.

**Why:** The map existed solely to route different types to different files. With a unified file, the map is dead code. A single constant is simpler and eliminates an entire category of "wrong workflow file" bugs.

**Example:**
```python
# constants.py
WORKFLOW_FILENAME = "ferry.yml"

# trigger.py
from ferry_utils.constants import WORKFLOW_FILENAME
workflow_file = WORKFLOW_FILENAME
```

### Pattern 3: Additive Output in parse_payload.py

**What:** Add `resource_type` as a second GHA output alongside the existing `matrix` output. Do not change `build_matrix()` or its return type.

**Why:** `build_matrix()` is well-tested (12 tests). Adding an output in `main()` is purely additive -- zero risk of breaking the matrix logic. The new output comes directly from the already-parsed `DispatchPayload.resource_type`.

**Example:**
```python
def main() -> None:
    # ... existing payload parse and matrix build ...
    payload = DispatchPayload.model_validate_json(payload_str)
    matrix = build_matrix(payload_str)
    matrix_json = json.dumps(matrix, separators=(",", ":"))
    set_output("matrix", matrix_json)
    set_output("resource_type", payload.resource_type)  # NEW
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Single Monolithic Dispatch

**What:** Sending one dispatch with ALL resource types combined in a single payload.

**Why bad:** Breaks the clean per-type matrix fan-out. A matrix containing lambda resources and SF resources would need type-checking in every step. The build step only applies to lambdas, so SF/APGW matrix entries would fail or need complex `if` conditions on every step.

**Instead:** Keep per-type dispatch (already working, proven in v1.0-v1.3).

### Anti-Pattern 2: Using `fromJson` Without Job-Level Guard

**What:** Putting the `if` condition on individual steps instead of the job.

**Why bad:** If the `if` is on steps but not the job, GHA still evaluates `matrix: ${{ fromJson(needs.setup.outputs.matrix) }}`. When the matrix shape doesn't match the expected fields (e.g., a SF payload being fed to a Lambda job), the job runs but steps fail confusingly. Worse, `fromJson` with certain empty or mismatched inputs can cause GHA runner errors.

**Instead:** Put `if` on the job itself. Skipped jobs never evaluate their matrix.

### Anti-Pattern 3: Creating a New "Router" Action

**What:** Building a new composite action that wraps all deploy types and routes internally.

**Why bad:** Over-engineering. The routing is naturally expressed in GHA workflow YAML via `if` conditions. Adding a router action creates an abstraction layer that hides logic from the user's workflow file, making debugging harder.

**Instead:** Let the workflow YAML be the router. Each deploy job is explicit about which action it calls.

### Anti-Pattern 4: Changing the Dispatch Payload Model

**What:** Adding a new field to `DispatchPayload` or changing how resources are structured to accommodate the unified workflow.

**Why bad:** The payload model is the shared contract between backend and action. It's correct as-is. The unified workflow is a user-side concern (workflow file structure), not a payload concern. Changing the model risks breaking the proven dispatch pipeline for no functional gain.

**Instead:** Leave `DispatchPayload` unchanged. Add `resource_type` as a GHA output derived from the existing field.

## Concurrency Considerations

| Scenario | Behavior | Notes |
|----------|----------|-------|
| Push changes 1 Lambda | 1 dispatch to ferry.yml, 1 run, only deploy-lambdas job runs | Identical to v1.3 |
| Push changes 3 Lambdas + 1 SF | 2 dispatches to ferry.yml, 2 parallel runs | GHA runs both in parallel by default (no concurrency group) |
| Push changes all 3 types | 3 dispatches to ferry.yml, 3 parallel runs | Each run's setup determines which deploy job runs |
| Rapid successive pushes | Multiple dispatches per push, all independent | No interference -- each dispatch has unique payload |

**Do NOT add a concurrency group** to the unified workflow. The v1.3 behavior (parallel per-type execution) is correct and should be preserved. Adding a concurrency group would serialize what are currently independent deploys, increasing total deployment time.

If users want to prevent concurrent deploys of the same resource, that is a v2.0 concern (deploy locking). The workflow-level concurrency group is the wrong mechanism for resource-level locking.

## Build Order (Implementation Sequence)

The changes have a clear dependency chain. The backend and action changes are independent of each other, but both must land before the user workflow template and docs can be finalized.

```
Phase 1: Backend + Action (parallel, no dependency between them)
  |
  |-- 1a. constants.py: Replace RESOURCE_TYPE_WORKFLOW_MAP with WORKFLOW_FILENAME
  |   |-- trigger.py: Use WORKFLOW_FILENAME
  |   |-- test_dispatch_trigger.py: Update expected workflow filenames
  |
  |-- 1b. parse_payload.py: Add resource_type output
  |   |-- setup/action.yml: Expose resource_type output
  |   |-- test_parse_payload.py: Add tests for resource_type output
  |
Phase 2: User workflow template + docs (depends on Phase 1)
  |
  |-- 2a. Create ferry.yml template (reference for docs)
  |-- 2b. Update docs/lambdas.md, docs/step-functions.md, docs/api-gateways.md
  |       (change workflow filename references from per-type to ferry.yml)
  |
Phase 3: Test repo update + E2E validation (depends on Phase 2)
  |
  |-- 3a. Replace 3 workflow files in test repo with single ferry.yml
  |-- 3b. Deploy backend with new WORKFLOW_FILENAME
  |-- 3c. Trigger test push, verify dispatch -> ferry.yml -> correct deploy job
```

**Why this order:**
1. **1a and 1b are independent.** `constants.py`/`trigger.py` changes don't affect `parse_payload.py` and vice versa. They can be developed and tested in parallel.
2. **Phase 2 depends on both 1a and 1b.** The workflow template references the setup action's `resource_type` output (from 1b), and the backend must dispatch to `ferry.yml` (from 1a) for it to work.
3. **Phase 3 is E2E validation.** Must happen after everything is deployed and the test repo is updated.

### Files Changed (Complete List)

| File | Action | Lines Changed (est.) | Risk |
|------|--------|---------------------|------|
| `utils/src/ferry_utils/constants.py` | Modify | -5, +2 | LOW -- removing a dict, adding a string |
| `backend/src/ferry_backend/dispatch/trigger.py` | Modify | -2, +2 (import + usage) | LOW -- simplification |
| `action/src/ferry_action/parse_payload.py` | Modify | +3 (parse + output) | LOW -- additive only |
| `action/setup/action.yml` | Modify | +3 (new output declaration) | LOW -- additive only |
| `tests/test_backend/test_dispatch_trigger.py` | Modify | ~15 lines (update workflow expectations) | LOW -- string changes |
| `tests/test_action/test_parse_payload.py` | Modify | +15-20 (new tests for resource_type) | LOW -- additive |
| `docs/lambdas.md` | Modify | ~5 lines (filename references) | LOW -- text changes |
| `docs/step-functions.md` | Modify | ~5 lines (filename references) | LOW -- text changes |
| `docs/api-gateways.md` | Modify | ~5 lines (filename references) | LOW -- text changes |
| Test repo workflows | Replace 3 files with 1 | ~120 lines total (new ferry.yml) | MEDIUM -- E2E validation needed |

## GHA Behavioral Verification

Key GHA behaviors that this architecture depends on, verified via GitHub documentation:

1. **Multiple dispatches to the same workflow file run in parallel** when no `concurrency` key is set. Each dispatch creates an independent workflow run. (Source: [GitHub Actions Concurrency Docs](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency))

2. **Job-level `if` conditions prevent matrix evaluation** for skipped jobs. When `if` evaluates to false, GHA skips the entire job including `strategy.matrix` evaluation. This means `fromJson` is never called with a mismatched payload. (Source: [GitHub Actions Using Conditions](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution))

3. **Skipped jobs report status "Success"** for required status check purposes. This means having 3 deploy jobs where 2 are always skipped does not break branch protection rules. (Source: [GitHub community discussion #60792](https://github.com/orgs/community/discussions/60792))

4. **`fromJson` with `{"include": []}` causes an error** if the matrix job is not guarded. The job-level `if` guard (Pattern 1) prevents this. (Source: [GitHub community discussion #27096](https://github.com/orgs/community/discussions/27096))

## Sources

- GitHub Actions Concurrency Documentation: https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency
- GitHub Actions Workflow Syntax: https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions
- GitHub Actions Conditions: https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution
- Empty matrix handling: https://github.com/orgs/community/discussions/27096
- Conditional jobs and status checks: https://github.com/orgs/community/discussions/60792
- Existing codebase analysis: `trigger.py`, `constants.py`, `parse_payload.py`, `setup/action.yml`, all three deploy action YAMLs, `handler.py`, existing test files
