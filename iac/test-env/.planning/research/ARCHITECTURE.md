# Architecture Patterns: v1.5 Batched Dispatch

**Domain:** Batched multi-type dispatch for serverless deploy tool (Ferry v1.5)
**Researched:** 2026-03-10

## Problem Statement

Currently (v1.4), when a push affects 3 Lambdas and 1 Step Function, the backend sends 2 separate `workflow_dispatch` events to `ferry.yml` -- one with `resource_type=lambda` carrying 3 resources, one with `resource_type=step_function` carrying 1 resource. This creates 2 workflow runs in the GHA UI, each with 2 skipped deploy jobs (the types that don't apply). A push affecting all 3 types produces 3 runs with 6 skipped jobs total. The user sees clutter.

v1.5 replaces this with a single dispatch containing ALL affected resource types. One push produces one workflow run. Only the relevant deploy jobs are active.

## Recommended Architecture

**Single dispatch per push, multi-type payload, per-type matrix outputs from setup job.**

The backend merges all affected resources (across all types) into a single `BatchedDispatchPayload`, sends one `workflow_dispatch` to `ferry.yml`. The setup action parses the payload and outputs separate matrices per type, plus boolean flags indicating which types have resources. Each deploy job gates on its boolean flag and consumes its own type-specific matrix.

```
BEFORE (v1.4):
  Push (3 lambdas + 1 SF changed)
    -> Backend groups by type
    -> Dispatch 1: POST ferry.yml  (resource_type=lambda, 3 resources)
    -> Dispatch 2: POST ferry.yml  (resource_type=step_function, 1 resource)
    -> GHA: 2 workflow runs, each with 2 skipped jobs = 4 skipped jobs visible

AFTER (v1.5):
  Push (3 lambdas + 1 SF changed)
    -> Backend collects ALL affected resources
    -> Dispatch 1: POST ferry.yml  (resources: {lambdas: [...], step_functions: [...]})
    -> GHA: 1 workflow run, setup + deploy-lambda + deploy-step-function active, deploy-api-gateway skipped
```

### Why This Approach

1. **Eliminates the core UX problem.** One push = one workflow run. No more 3 identical "Ferry Deploy" runs.
2. **The v1.4 anti-pattern is now the solution.** v1.4 FEATURES.md explicitly called out "merging all types into a single dispatch" as an anti-feature because it would "require backend rework." That rework is exactly what v1.5 is for. The v1.4 architecture (per-type dispatch + `if: resource_type == X`) was the right stepping stone. The conditional job routing pattern established in v1.4 is preserved -- only the gating mechanism changes from `resource_type` string comparison to boolean flags.
3. **Stays within GHA constraints.** Each deploy job still has a single-type matrix. No mixed-type matrix. No dynamic job creation. The workflow YAML structure is nearly identical to v1.4.

## Component Boundaries

| Component | Responsibility | Change Type | Risk |
|-----------|---------------|-------------|------|
| `ferry_utils/models/dispatch.py` | Dispatch payload Pydantic models | **MODIFY**: Add `BatchedDispatchPayload` model | MEDIUM |
| `ferry_utils/constants.py` | Schema version constant | **MODIFY**: Bump `SCHEMA_VERSION` to 2 | LOW |
| `ferry_backend/dispatch/trigger.py` | Groups resources, builds payload, POSTs dispatch | **MODIFY**: Merge all types into single dispatch | MEDIUM |
| `ferry_action/parse_payload.py` | Parses payload, builds GHA matrix outputs | **MODIFY**: Output per-type matrices + boolean flags | MEDIUM |
| `action/setup/action.yml` | Composite action declaring outputs | **MODIFY**: Declare new outputs | LOW |
| `ferry.yml` (user workflow) | Workflow template with conditional jobs | **MODIFY**: Gate on booleans, use per-type matrices | LOW |
| `docs/setup.md` | Workflow template documentation | **MODIFY**: Update template and dispatch description | LOW |
| Test repo workflow | User-side `ferry.yml` | **MODIFY**: Update to v1.5 template | LOW |
| Tests (dispatch, parse, models) | Unit tests for all changed modules | **MODIFY**: Update all test assertions | MEDIUM |

## New Data Models

### BatchedDispatchPayload (NEW)

Replaces the per-type `DispatchPayload`. Contains resources grouped by type within a single payload.

```python
class BatchedDispatchPayload(BaseModel):
    """Payload sent via workflow_dispatch from Ferry App to Ferry Action.

    Single payload per push event. Contains all affected resources
    grouped by type. Replaces per-type DispatchPayload.
    """
    model_config = ConfigDict(frozen=True)

    v: int = SCHEMA_VERSION  # 2
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
```

**Key design decisions:**

1. **Per-type lists instead of a flat `resources` list.** The current `DispatchPayload` has a single `resources: list[Resource]` with a discriminated union. The batched model uses named lists (`lambdas`, `step_functions`, `api_gateways`) because the parse_payload action needs to output separate matrices per type. Named lists eliminate the need to filter by `resource_type` on the action side -- each list is already typed.

2. **Drop the top-level `resource_type` field.** It no longer makes sense when a payload carries multiple types. The boolean flags (`has_lambdas`, `has_step_functions`, `has_api_gateways`) replace it for job routing.

3. **Bump schema version to 2.** The `v` field distinguishes old vs new payloads. The parse_payload action can support both during migration (check `v`, dispatch to old or new parser).

4. **Keep existing resource models unchanged.** `LambdaResource`, `StepFunctionResource`, `ApiGatewayResource` are all preserved exactly as-is. They are the stable shared contract for individual resource descriptions.

### Backward Compatibility

The old `DispatchPayload` (v=1) should be retained for at least one release cycle. The `parse_payload.py` main function checks `v` and dispatches:

```python
raw = json.loads(payload_str)
version = raw.get("v", 1)
if version >= 2:
    return parse_batched_payload(payload_str)
else:
    return parse_legacy_payload(payload_str)  # existing build_matrix()
```

This is purely defensive. Since Ferry controls both ends (backend + action), they deploy together, so in practice both sides upgrade simultaneously. But having backward compat costs almost nothing and prevents breakage if the action updates before the backend (or vice versa during a partial deploy).

## Data Flow: End to End

### Backend (ferry-backend)

```
handler.py receives push webhook
  -> detect/changes.py: match_resources() returns list[AffectedResource]
     (each has: name, resource_type, change_kind, changed_files)
  -> dispatch/trigger.py: trigger_batched_dispatch()
     -> Group resources by type (same as today)
     -> Build typed resource lists:
        lambdas = [_build_resource("lambda", r.name, config) for r in lambda_affected]
        step_functions = [_build_resource("step_function", r.name, config) for r in sf_affected]
        api_gateways = [_build_resource("api_gateway", r.name, config) for r in ag_affected]
     -> Construct BatchedDispatchPayload(
          v=2,
          lambdas=lambdas,
          step_functions=step_functions,
          api_gateways=api_gateways,
          trigger_sha=sha,
          deployment_tag=tag,
          pr_number=pr_number,
        )
     -> Check payload size (same 65535 limit)
     -> POST /repos/{repo}/actions/workflows/ferry.yml/dispatches
        body: {ref: default_branch, inputs: {payload: payload.model_dump_json()}}
  -> Returns: [{"status": 204, "workflow": "ferry.yml", "types": ["lambda", "step_function"]}]
```

**Key change in trigger.py:** The `for rtype, resources in grouped.items()` loop that currently sends N dispatches becomes a single construction of `BatchedDispatchPayload` followed by a single `client.post()`. The grouping logic stays (it still needs to build typed resource lists), but the loop over types for dispatch goes away.

### Setup Action (ferry-action)

```
ferry.yml workflow_dispatch fires
  -> setup job runs
  -> parse_payload.py reads INPUT_PAYLOAD
  -> Parses as BatchedDispatchPayload (v=2)
  -> Builds per-type matrices:
     lambda_matrix = {"include": [_lambda_entry(r) for r in payload.lambdas]}
     sf_matrix = {"include": [_sf_entry(r) for r in payload.step_functions]}
     ag_matrix = {"include": [_ag_entry(r) for r in payload.api_gateways]}
  -> Outputs to GITHUB_OUTPUT:
     has_lambdas = "true" / "false"
     has_step_functions = "true" / "false"
     has_api_gateways = "true" / "false"
     lambda_matrix = JSON string (or empty {"include":[]})
     sf_matrix = JSON string (or empty {"include":[]})
     ag_matrix = JSON string (or empty {"include":[]})
     resource_types = "lambda,step_function"  (comma-separated, for run-name display)
```

**Key design: separate outputs per type.** Each deploy job reads its own matrix output. The boolean flags gate whether the job runs at all (preventing the empty-matrix `fromJson` crash documented in v1.4 Pitfall 3). The `resource_types` output is a convenience for the workflow `run-name`.

### User Workflow (ferry.yml)

```yaml
name: Ferry Deploy
run-name: "Ferry: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).v >= 2 && 'deploy' || fromJson(github.event.inputs.payload).resource_type || 'manual' }}"

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON) -- sent by Ferry App"
        required: true

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      has_lambdas: ${{ steps.parse.outputs.has_lambdas }}
      has_step_functions: ${{ steps.parse.outputs.has_step_functions }}
      has_api_gateways: ${{ steps.parse.outputs.has_api_gateways }}
      lambda_matrix: ${{ steps.parse.outputs.lambda_matrix }}
      sf_matrix: ${{ steps.parse.outputs.sf_matrix }}
      ag_matrix: ${{ steps.parse.outputs.ag_matrix }}
      resource_types: ${{ steps.parse.outputs.resource_types }}
    steps:
      - uses: actions/checkout@v4
      - id: parse
        uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambda:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_lambdas == 'true'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-lambda
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
      fail-fast: false
    steps:
      # ... same build + deploy steps as v1.4 ...

  deploy-step-function:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_step_functions == 'true'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-step-function
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.sf_matrix) }}
      fail-fast: false
    steps:
      # ... same deploy-stepfunctions steps as v1.4 ...

  deploy-api-gateway:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_api_gateways == 'true'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-api-gateway
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.ag_matrix) }}
      fail-fast: false
    steps:
      # ... same deploy-apigw steps as v1.4 ...
```

**Key changes from v1.4 workflow:**
1. `if` conditions change from `needs.setup.outputs.resource_type == 'lambda'` to `needs.setup.outputs.has_lambdas == 'true'`
2. Each deploy job uses its own matrix output (`lambda_matrix`, `sf_matrix`, `ag_matrix`) instead of a shared `matrix`
3. `run-name` can show all affected types since the payload contains all of them
4. Multiple deploy jobs now run in the same workflow run (not separate runs)

### Why Booleans Instead of Empty-Matrix Checks

The v1.4 PITFALLS.md (Pitfall 3) documented that `fromJson` on `{"include":[]}` crashes GHA. The boolean flags (`has_lambdas == 'true'`) are the guard that prevents the matrix from being evaluated when empty. This pattern was explicitly recommended in v1.4 research as a "differentiator" -- now it becomes table stakes because the batched model guarantees some type lists will be empty.

Alternative considered: `if: needs.setup.outputs.lambda_matrix != '{"include":[]}'` -- rejected because string comparison with JSON is fragile and harder to read.

## Detailed Changes Per File

### 1. `utils/src/ferry_utils/models/dispatch.py` -- MODIFY

**Add `BatchedDispatchPayload`:**

```python
class BatchedDispatchPayload(BaseModel):
    """Batched dispatch payload -- single dispatch per push, all types included."""

    model_config = ConfigDict(frozen=True)

    v: int = 2
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
```

**Keep `DispatchPayload` for backward compatibility** (will be removed in a future version). Keep all resource models (`LambdaResource`, `StepFunctionResource`, `ApiGatewayResource`) unchanged.

**Update `__init__.py` re-exports** to include `BatchedDispatchPayload`.

### 2. `utils/src/ferry_utils/constants.py` -- MODIFY

```python
SCHEMA_VERSION = 2  # was 1
```

### 3. `backend/src/ferry_backend/dispatch/trigger.py` -- MODIFY

Replace the loop-over-types dispatch with a single batched dispatch. The function signature changes to emphasize the batching:

```python
def trigger_dispatch(  # singular, not plural
    client: GitHubClient,
    repo: str,
    config: FerryConfig,
    affected: list[AffectedResource],
    sha: str,
    deployment_tag: str,
    pr_number: str,
    default_branch: str = "main",
) -> dict:
    """Fire a single workflow_dispatch containing all affected resource types.

    Returns:
        Result dict: {"status": int, "workflow": str, "types": list[str]}.
    """
    if not affected:
        return {"status": 0, "workflow": "", "types": []}

    # Group by resource type (same logic as before)
    grouped: dict[str, list[AffectedResource]] = {}
    for resource in affected:
        grouped.setdefault(resource.resource_type, []).append(resource)

    # Build typed resource lists
    lambdas = [_build_resource("lambda", r.name, config)
               for r in grouped.get("lambda", [])]
    step_functions = [_build_resource("step_function", r.name, config)
                      for r in grouped.get("step_function", [])]
    api_gateways = [_build_resource("api_gateway", r.name, config)
                    for r in grouped.get("api_gateway", [])]

    payload = BatchedDispatchPayload(
        lambdas=lambdas,
        step_functions=step_functions,
        api_gateways=api_gateways,
        trigger_sha=sha,
        deployment_tag=deployment_tag,
        pr_number=pr_number,
    )

    payload_json = payload.model_dump_json()
    if len(payload_json) > _MAX_PAYLOAD_SIZE:
        logger.error("dispatch_payload_too_large", size=len(payload_json))
        return {"status": 413, "workflow": WORKFLOW_FILENAME, "types": list(grouped.keys())}

    resp = client.post(
        f"/repos/{repo}/actions/workflows/{WORKFLOW_FILENAME}/dispatches",
        json={"ref": default_branch, "inputs": {"payload": payload_json}},
    )

    types = list(grouped.keys())
    logger.info("dispatch_triggered", types=types, status=resp.status_code)
    return {"status": resp.status_code, "workflow": WORKFLOW_FILENAME, "types": types}
```

**What changes:**
- Function name: `trigger_dispatches` (plural, returns list) becomes `trigger_dispatch` (singular, returns dict)
- No more loop over `grouped.items()` to send multiple POSTs
- Payload construction builds all three type lists at once
- Return type simplifies from `list[dict]` to `dict`

**What stays the same:**
- `_build_resource()` helper -- unchanged
- `build_deployment_tag()` -- unchanged
- Grouping logic -- still groups by type, just doesn't iterate to dispatch

### 4. `backend/src/ferry_backend/webhook/handler.py` -- MODIFY (minimal)

The handler currently calls `trigger_dispatches()` (plural). Update to `trigger_dispatch()` (singular):

```python
# Line ~202, currently:
trigger_dispatches(client, repo, config, affected, after_sha, tag, pr_number, default_branch=default_branch)

# Becomes:
result = trigger_dispatch(client, repo, config, affected, after_sha, tag, pr_number, default_branch=default_branch)
```

The log line at ~214 also simplifies since we now have one dispatch result instead of counting unique types from a result list.

### 5. `action/src/ferry_action/parse_payload.py` -- MODIFY

Replace `build_matrix()` (single-type matrix) with `build_batched_outputs()` (multi-type outputs):

```python
def build_batched_outputs(payload_str: str) -> dict:
    """Parse batched dispatch payload and build per-type GHA outputs.

    Returns dict with keys:
      has_lambdas, has_step_functions, has_api_gateways (bool as str)
      lambda_matrix, sf_matrix, ag_matrix (JSON strings)
      resource_types (comma-separated string)
    """
    payload = BatchedDispatchPayload.model_validate_json(payload_str)

    lambda_entries = [_lambda_entry(r, payload) for r in payload.lambdas]
    sf_entries = [_sf_entry(r, payload) for r in payload.step_functions]
    ag_entries = [_ag_entry(r, payload) for r in payload.api_gateways]

    types_present = []
    if lambda_entries:
        types_present.append("lambda")
    if sf_entries:
        types_present.append("step_function")
    if ag_entries:
        types_present.append("api_gateway")

    return {
        "has_lambdas": str(bool(lambda_entries)).lower(),
        "has_step_functions": str(bool(sf_entries)).lower(),
        "has_api_gateways": str(bool(ag_entries)).lower(),
        "lambda_matrix": json.dumps({"include": lambda_entries}, separators=(",", ":")),
        "sf_matrix": json.dumps({"include": sf_entries}, separators=(",", ":")),
        "ag_matrix": json.dumps({"include": ag_entries}, separators=(",", ":")),
        "resource_types": ",".join(types_present),
    }
```

The existing `_build_lambda_matrix`, `_build_step_function_matrix`, `_build_api_gateway_matrix` helper functions become the `_lambda_entry`, `_sf_entry`, `_ag_entry` helpers (same logic, just renamed/refactored to build entries instead of full matrices).

**`main()` function updates:**

```python
def main() -> None:
    payload_str = os.environ.get("INPUT_PAYLOAD")
    if not payload_str:
        error("INPUT_PAYLOAD not set or empty")
        sys.exit(1)

    try:
        raw = json.loads(payload_str)
        version = raw.get("v", 1)

        if version >= 2:
            outputs = build_batched_outputs(payload_str)
            for key, value in outputs.items():
                set_output(key, value)
        else:
            # Legacy v1 payload support
            matrix = build_matrix(payload_str)
            set_output("matrix", json.dumps(matrix, separators=(",", ":")))
            payload = DispatchPayload.model_validate_json(payload_str)
            set_output("resource_type", payload.resource_type)

    except Exception as exc:
        error(f"Failed to parse dispatch payload: {exc}")
        sys.exit(1)
```

### 6. `action/setup/action.yml` -- MODIFY

Add all new outputs:

```yaml
outputs:
  # v1.5 batched outputs
  has_lambdas:
    description: "Whether the payload contains Lambda resources"
    value: ${{ steps.parse.outputs.has_lambdas }}
  has_step_functions:
    description: "Whether the payload contains Step Function resources"
    value: ${{ steps.parse.outputs.has_step_functions }}
  has_api_gateways:
    description: "Whether the payload contains API Gateway resources"
    value: ${{ steps.parse.outputs.has_api_gateways }}
  lambda_matrix:
    description: "JSON matrix for Lambda deploy jobs"
    value: ${{ steps.parse.outputs.lambda_matrix }}
  sf_matrix:
    description: "JSON matrix for Step Function deploy jobs"
    value: ${{ steps.parse.outputs.sf_matrix }}
  ag_matrix:
    description: "JSON matrix for API Gateway deploy jobs"
    value: ${{ steps.parse.outputs.ag_matrix }}
  resource_types:
    description: "Comma-separated list of affected resource types"
    value: ${{ steps.parse.outputs.resource_types }}
  # Legacy v1 outputs (kept for backward compat)
  matrix:
    description: "JSON string for fromJson() in GHA strategy matrix (v1 legacy)"
    value: ${{ steps.parse.outputs.matrix }}
  resource_type:
    description: "Resource type string (v1 legacy)"
    value: ${{ steps.parse.outputs.resource_type }}
```

## Patterns to Follow

### Pattern 1: Boolean Gating for Conditional Matrix Jobs

**What:** Each deploy job checks a boolean output (`has_lambdas == 'true'`) before running. This prevents GHA from evaluating `fromJson` on an empty matrix.

**Why:** GHA crashes when `strategy.matrix` receives `{"include":[]}`. The boolean guard ensures the job is skipped entirely when no resources of that type exist, so the matrix expression is never evaluated.

**Example:**
```yaml
deploy-lambda:
  needs: setup
  if: needs.setup.outputs.has_lambdas == 'true'
  strategy:
    matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
```

### Pattern 2: Named Type Lists in Payload Model

**What:** The batched payload uses named fields (`lambdas`, `step_functions`, `api_gateways`) instead of a single `resources` list with a discriminator.

**Why:** Named lists make the parse_payload code simpler -- no filtering by resource_type needed. Each field is already a typed list. This also makes the Pydantic model self-documenting and produces cleaner JSON.

**Example:**
```python
# Clear, typed access:
for r in payload.lambdas:  # list[LambdaResource]
    ...

# vs. v1 discriminated union filtering:
for r in payload.resources:
    if isinstance(r, LambdaResource):
        ...
```

### Pattern 3: Version-Aware Payload Parsing

**What:** The parse_payload action checks `v` field to dispatch to the correct parser.

**Why:** Enables zero-downtime upgrades. During the transition, if the action deploys before the backend, it can still handle v1 payloads. If the backend deploys first, the v2 payload is understood by the updated action.

**Example:**
```python
version = raw.get("v", 1)
if version >= 2:
    outputs = build_batched_outputs(payload_str)
else:
    # Legacy path
    matrix = build_matrix(payload_str)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Mixed-Type Matrix

**What:** Putting all resources (lambdas + SFs + APGWs) into a single matrix and using step-level `if` conditions to route.

**Why bad:** A matrix entry for a Lambda has `ecr`, `function_name`, `runtime`. A matrix entry for an SF has `state_machine_name`, `definition_file`. These have different fields. Mixing them into one matrix means either: (a) every entry has all possible fields with empty strings for inapplicable ones (brittle, confusing), or (b) complex step-level `if` conditions checking resource type before each step. Both approaches make the workflow unreadable and error-prone.

**Instead:** Separate matrices per type. Each deploy job's matrix entries have only the fields relevant to that type.

### Anti-Pattern 2: Multiple workflow_dispatch Inputs

**What:** Using separate `workflow_dispatch` inputs per type (`lambda_payload`, `sf_payload`, `ag_payload`).

**Why bad:** GHA limits to 25 inputs total, and each input is a string. Splitting the payload into multiple inputs adds complexity in the backend (which inputs to fill) and the setup action (which inputs to read). A single JSON payload is simpler and the 65535 char limit is shared across all inputs anyway.

**Instead:** Single `payload` input containing the entire `BatchedDispatchPayload` as JSON.

### Anti-Pattern 3: Dynamic Job Generation

**What:** Generating job definitions at runtime based on which types are in the payload.

**Why bad:** GHA does not support dynamic job creation. Jobs must be statically defined in the YAML. The only dynamic elements are `if` conditions and `strategy.matrix` values.

**Instead:** Define all 3 deploy jobs statically. Use boolean `if` gates to skip irrelevant ones.

### Anti-Pattern 4: Removing the Legacy DispatchPayload Immediately

**What:** Deleting the v1 `DispatchPayload` model and `build_matrix()` function in the same commit as adding batched support.

**Why bad:** If the action and backend deploy at slightly different times, one side may send/receive v1 payloads while the other expects v2. Retaining the legacy path costs 50 lines and eliminates an entire class of deployment-order bugs.

**Instead:** Keep both, route by version, remove v1 in a later cleanup commit after v1.5 is proven in production.

## Concurrency Model

With batched dispatch, the concurrency picture changes favorably:

| Scenario | v1.4 (per-type dispatch) | v1.5 (batched dispatch) |
|----------|-------------------------|------------------------|
| Push changes all 3 types | 3 workflow runs, 6 skipped jobs | 1 workflow run, 0 skipped jobs |
| Push changes 1 Lambda | 1 workflow run, 2 skipped jobs | 1 workflow run, 2 skipped jobs |
| Push changes 2 Lambdas + 1 SF | 2 workflow runs, 4 skipped jobs | 1 workflow run, 1 skipped job |
| Rapid double push | 6 workflow runs (worst case) | 2 workflow runs |

**Concurrency groups remain job-level** (per v1.4 design). With batched dispatch, the risk of parallel multi-type dispatches canceling each other (v1.4 Pitfall 1) is eliminated because there is only one dispatch per push.

However, rapid successive pushes can still produce concurrent workflow runs. The per-type job-level concurrency groups (`ferry-deploy-lambda`, `ferry-deploy-step-function`, `ferry-deploy-api-gateway`) handle this correctly: each type queues independently. A second push's Lambda deploy waits for the first push's Lambda deploy, but Step Function deploys from both pushes can overlap (which is safe since they deploy independent resources).

## Payload Size Analysis

The 65535 character limit applies to all `workflow_dispatch` inputs combined. With batched dispatch, the payload is larger than any single per-type payload was, but still well within limits for realistic workloads.

**Estimation per resource type (approximate JSON size):**
- LambdaResource: ~150 chars (name + source + ecr + function_name + runtime + type literal)
- StepFunctionResource: ~130 chars (name + source + state_machine_name + definition_file + type literal)
- ApiGatewayResource: ~140 chars (name + source + rest_api_id + stage_name + spec_file + type literal)
- Payload envelope: ~100 chars (v, trigger_sha, deployment_tag, pr_number, field names)

**Practical limits (conservative):**
- 50 Lambdas + 20 SFs + 10 APGWs = ~14,000 chars. Well under 65535.
- Maximum resources before hitting limit: approximately 350-400 resources total.

The existing `_MAX_PAYLOAD_SIZE` check in `trigger.py` still applies and handles the edge case. For users who somehow exceed the limit, the backend could split into multiple dispatches (future enhancement, not needed for v1.5).

## Build Order (Implementation Sequence)

The changes have a clear dependency chain. The shared models must be updated first since both backend and action depend on them.

```
Phase 1: Shared Models (foundation -- everything depends on this)
  |
  |-- 1a. dispatch.py: Add BatchedDispatchPayload model
  |-- 1b. constants.py: Bump SCHEMA_VERSION to 2
  |-- 1c. __init__.py: Re-export new model
  |-- 1d. test_dispatch_models.py: Tests for new model
  |
Phase 2: Backend Dispatch + Action Parse (parallel, independent of each other)
  |
  |-- 2a. trigger.py: Replace trigger_dispatches() with trigger_dispatch()
  |   |-- handler.py: Update call site (trigger_dispatches -> trigger_dispatch)
  |   |-- test_dispatch_trigger.py: Rewrite dispatch tests for single-dispatch model
  |   |-- test_handler_phase2.py: Update handler integration tests
  |
  |-- 2b. parse_payload.py: Add build_batched_outputs(), version routing in main()
  |   |-- setup/action.yml: Declare all new outputs
  |   |-- test_parse_payload.py: Tests for batched output generation + v1 compat
  |
Phase 3: Workflow Template + Docs (depends on Phase 2 for output names)
  |
  |-- 3a. Update ferry.yml template (boolean gates, per-type matrices)
  |-- 3b. Update docs/setup.md (new template, new dispatch description)
  |
Phase 4: Test Repo + E2E Validation (depends on all above)
  |
  |-- 4a. Update test repo ferry.yml to v1.5 template
  |-- 4b. Deploy backend with batched dispatch
  |-- 4c. Push test changes, verify single workflow run with correct jobs active
  |-- 4d. Push multi-type change, verify all 3 deploy jobs run in one workflow
```

### Why This Order

1. **Phase 1 first** because `BatchedDispatchPayload` is imported by both backend and action. Both need the model to exist before they can write code against it.
2. **Phase 2a and 2b are independent.** Backend dispatch logic does not import parse_payload, and vice versa. They share only the model from Phase 1.
3. **Phase 3 depends on Phase 2** because the workflow template references specific output names from the setup action (decided in 2b) and assumes the backend sends batched payloads (decided in 2a).
4. **Phase 4 is E2E validation.** Must be last. The backend must be deployed with new dispatch logic, the test repo must have the new workflow template, and both must be on the same version.

### Files Changed (Complete List)

| File | Action | Estimated Changes | Risk |
|------|--------|------------------|------|
| `utils/src/ferry_utils/models/dispatch.py` | Modify | +20 lines (new model) | LOW |
| `utils/src/ferry_utils/models/__init__.py` | Modify | +1 line (re-export) | LOW |
| `utils/src/ferry_utils/constants.py` | Modify | 1 line (version bump) | LOW |
| `backend/src/ferry_backend/dispatch/trigger.py` | Modify | -30, +30 (rewrite dispatch loop) | MEDIUM |
| `backend/src/ferry_backend/webhook/handler.py` | Modify | ~5 lines (call site update) | LOW |
| `action/src/ferry_action/parse_payload.py` | Modify | +60 lines (batched parser + version routing) | MEDIUM |
| `action/setup/action.yml` | Modify | +20 lines (new output declarations) | LOW |
| `tests/test_utils/test_dispatch_models.py` | Modify | +30 lines (new model tests) | LOW |
| `tests/test_backend/test_dispatch_trigger.py` | Modify | Rewrite (~100 lines changed) | MEDIUM |
| `tests/test_backend/test_handler_phase2.py` | Modify | ~10 lines (call site updates) | LOW |
| `tests/test_action/test_parse_payload.py` | Modify | +60 lines (batched output tests + v1 compat) | MEDIUM |
| `docs/setup.md` | Modify | ~40 lines (new template, new description) | LOW |
| Test repo `ferry.yml` | Modify | ~20 lines (new output references) | LOW |

## GHA Behavioral Verification

Key GHA behaviors that this architecture depends on, verified:

1. **Multiple outputs from a single step are all available to downstream jobs.** The setup step writes 9+ outputs (booleans, matrices, resource_types). GHA step outputs have no practical count limit (the 25-input limit applies to `workflow_dispatch` inputs, not step outputs). **Confidence: HIGH** -- standard GHA feature.

2. **Boolean string comparison in `if` conditions works.** `if: needs.setup.outputs.has_lambdas == 'true'` correctly evaluates. GHA outputs are always strings; comparing with `== 'true'` is the standard pattern. **Confidence: HIGH** -- documented GHA behavior.

3. **Per-type matrix outputs work independently.** Each deploy job references its own matrix output (`lambda_matrix`, `sf_matrix`, `ag_matrix`). These are independent strings. No interference between them. **Confidence: HIGH** -- standard GHA pattern for dynamic matrices from setup job.

4. **Multiple deploy jobs run in parallel within the same workflow run.** When `has_lambdas`, `has_step_functions`, and `has_api_gateways` are all `'true'`, all three deploy jobs start after setup completes. They each have `needs: setup` but no dependency on each other, so GHA runs them in parallel. **Confidence: HIGH** -- documented GHA dependency behavior.

5. **Skipped jobs from `if: false` do not affect sibling jobs.** If `has_api_gateways == 'false'`, the APGW job is skipped, but the Lambda and SF jobs still run normally (they don't depend on the APGW job). **Confidence: HIGH** -- confirmed, skipped jobs report "Success" status.

6. **Workflow_dispatch input size limit is 65535 chars.** The batched payload must fit within this. Verified: 65535 chars total across all inputs (we use only one input: `payload`). **Confidence: HIGH** -- confirmed by [community discussion](https://github.com/orgs/community/discussions/120093) and existing code.

## Sources

- [GitHub Docs: Workflow syntax -- workflow_dispatch](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) -- input limits, run-name syntax (HIGH confidence)
- [GitHub Docs: Running variations of jobs -- dynamic matrix](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) -- fromJson matrix pattern (HIGH confidence)
- [GitHub Docs: Using conditions for job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) -- job-level if, skipped behavior (HIGH confidence)
- [GitHub Community: Dynamic matrix empty array crash](https://github.com/orgs/community/discussions/27096) -- empty fromJson crashes, boolean guard needed (MEDIUM confidence)
- [GitHub Community: workflow_dispatch input limits](https://github.com/orgs/community/discussions/120093) -- 25 inputs, 65535 chars total (MEDIUM confidence)
- [GitHub Blog: Workflow dispatch now supports 25 inputs](https://github.blog/changelog/2025-12-04-actions-workflow-dispatch-workflows-now-support-25-inputs/) -- input count limit increase (HIGH confidence)
- [GitHub Community: success() returns false if dependent jobs are skipped](https://github.com/orgs/community/discussions/45058) -- skipped job cascade behavior (MEDIUM confidence)
- Existing codebase analysis: `trigger.py`, `parse_payload.py`, `dispatch.py` models, `handler.py`, `setup/action.yml`, `ferry.yml` template, all test files (PRIMARY source)
- v1.4 research: `ARCHITECTURE.md`, `PITFALLS.md`, `FEATURES.md` -- patterns and anti-patterns that inform v1.5 design (PRIMARY source)
