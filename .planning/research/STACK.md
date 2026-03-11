# Technology Stack: Ferry v1.5 Batched Dispatch

**Project:** Ferry - Batch all affected resource types into a single workflow_dispatch
**Researched:** 2026-03-10
**Overall confidence:** HIGH (constraints verified against official GitHub docs, existing codebase analyzed directly, Pydantic v2 behavior verified)

## Scope

This STACK.md covers ONLY what changes or gets added for batched dispatch. The existing stack (Python 3.14, httpx, PyJWT+cryptography, boto3, Pydantic v2, structlog, uv workspace) is shipped and validated -- not re-researched here.

## Key Finding: No New Libraries Required

Batched dispatch is a payload schema change + workflow template change + setup action logic change. Every tool needed already exists in the codebase. No new pip dependencies. No new GitHub Actions. No new infrastructure.

---

## GitHub Actions Constraints (Verified)

These constraints govern the entire design. All verified against official GitHub documentation.

| Constraint | Value | Source | Confidence |
|------------|-------|--------|------------|
| Max `inputs` payload size | 65,535 characters | [GitHub Docs: Events that trigger workflows](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows) | HIGH |
| Max number of inputs | 25 | Same source | HIGH |
| Per-input value limit (UI) | 1,024 characters | [Community Discussion #120093](https://github.com/orgs/community/discussions/120093) | MEDIUM |
| Per-input value limit (API) | Not documented separately; 65,535 total applies | Official docs only specify total payload limit | HIGH |
| Empty matrix behavior | Job fails with "does not contain any values" | [Community Discussion #27096](https://github.com/orgs/community/discussions/27096) | HIGH |

### Payload Size Analysis

The 65,535 character total payload limit is the binding constraint. Ferry sends dispatch via the REST API (not UI), so the 1,024 per-input UI limit does not apply. The existing code already enforces a 65,535 max (`_MAX_PAYLOAD_SIZE` in `trigger.py`).

Realistic payload sizes for batched dispatch (measured from simulated payloads):

| Scenario | Current (per-type) | Batched (all types) | % of Limit |
|----------|-------------------|---------------------|------------|
| Typical (2 lambdas + 1 SF + 1 APGW) | ~500 chars x 3 dispatches | ~724 chars x 1 dispatch | 1.1% |
| Large (20 lambdas + 10 SFs + 5 APGWs) | N/A (split by type) | ~5,319 chars | 8.1% |
| Extreme (100 lambdas, long names) | N/A | ~23,683 chars | 36.1% |
| Pathological (200 lambdas, long names) | N/A | ~47,683 chars | 72.8% |

**Conclusion:** The 65,535 limit is not a practical concern. Even pathological cases with 200 resources fit comfortably. No chunking, compression, or multi-input strategies needed. Keep the single `payload` input approach.

### Empty Matrix Handling

GitHub Actions crashes (not skips) when `fromJson` produces a matrix with zero elements. The current workflow already handles this via `if: needs.setup.outputs.resource_type == 'lambda'` guards on each deploy job. The batched approach must replace these guards.

**Required pattern for batched dispatch:**

```yaml
deploy-lambda:
  needs: setup
  if: needs.setup.outputs.has_lambdas == 'true'
  strategy:
    matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
```

The `if` guard prevents the job from evaluating the matrix expression at all. Comparing a string output to `'true'` (not comparing a matrix to `'[]'`) is the most reliable pattern per GitHub community guidance. Alternative: `needs.setup.outputs.lambda_matrix != '{"include":[]}'` -- works but is more fragile.

---

## Pydantic v2 Model Changes (No New Dependencies)

### Current Model: `DispatchPayload` (v1)

```python
class DispatchPayload(BaseModel):
    v: int = 1
    resource_type: str              # "lambda" | "step_function" | "api_gateway"
    resources: list[Resource]       # All same type (discriminated union)
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
```

One dispatch per type. The `resource_type` field tells the action which matrix builder to use. The `resources` list uses a discriminated union but only ever contains one type per payload.

### New Model: `BatchedDispatchPayload` (v2)

```python
class BatchedDispatchPayload(BaseModel):
    v: int = 2
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
```

**Why this structure over alternatives:**

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Keep `resources: list[Resource]` with mixed types | Minimal model change | Action must re-sort by type; discriminated union in list has known Pydantic JSON schema issues ([#6884](https://github.com/pydantic/pydantic/issues/6884)) | NO |
| Separate typed lists (`lambdas`, `step_functions`, `api_gateways`) | Type-safe, no sorting needed, no discriminator issues, each list maps directly to one matrix output | Three fields instead of one | YES |
| Nested dict `{"lambda": [...], "step_function": [...]}` | Flexible | Loses Pydantic type safety, harder to validate | NO |

**Key Pydantic v2 behaviors leveraged:**

- `list[LambdaResource] = []` -- empty list default means absent types produce `[]` not `null` in JSON. Already validated pattern in `FerryConfig`.
- `model_dump_json()` with `exclude_defaults=False` (the default) serializes empty lists as `[]`, ensuring the action always sees the field.
- Frozen models (`ConfigDict(frozen=True)`) already on all resource models -- no change needed.
- The `resource_type` discriminator field on individual resources (`Literal["lambda"]`, etc.) is no longer needed for routing but is harmless to keep for debugging/logging.

### Schema Version Bump

Bump `SCHEMA_VERSION` from `1` to `2` in `ferry_utils/constants.py`. The `v` field in the payload allows the action to detect payload version and handle both formats during migration if needed. In practice, the backend and action deploy together, so dual-version support is optional.

### No Need for `resource_type` at Payload Level

The v1 payload has `resource_type: str` at the top level because there is one dispatch per type. The v2 payload does not need this -- the setup action inspects which lists are non-empty. Removing `resource_type` from the payload simplifies the model. The setup action outputs per-type boolean flags (`has_lambdas`, `has_step_functions`, `has_api_gateways`) for workflow job routing.

---

## Setup Action Changes (No New Dependencies)

### Current: Single Matrix Output

The setup action (`parse_payload.py`) currently:
1. Reads `INPUT_PAYLOAD` env var
2. Validates against `DispatchPayload`
3. Calls the type-specific matrix builder based on `resource_type`
4. Outputs `matrix` (one JSON string) and `resource_type` (one string)

### New: Multiple Matrix Outputs

The setup action will:
1. Read `INPUT_PAYLOAD` env var
2. Validate against `BatchedDispatchPayload`
3. Build a matrix for each non-empty resource type list
4. Output per-type matrices and boolean flags:
   - `lambda_matrix` -- JSON string for Lambda `fromJson()`
   - `step_function_matrix` -- JSON string for SF `fromJson()`
   - `api_gateway_matrix` -- JSON string for APGW `fromJson()`
   - `has_lambdas` -- `"true"` or `"false"`
   - `has_step_functions` -- `"true"` or `"false"`
   - `has_api_gateways` -- `"true"` or `"false"`

**Why boolean flags instead of checking matrix emptiness:**
- GHA expression `needs.setup.outputs.has_lambdas == 'true'` is cleaner than `needs.setup.outputs.lambda_matrix != '{"include":[]}'`
- String comparison is well-tested in GHA; JSON comparison is brittle
- Boolean flags are a common pattern in the GHA ecosystem

**Implementation in `gha.py`:** Already has `set_output(name, value)` which writes to `$GITHUB_OUTPUT`. No changes needed to the helper -- just call it more times.

### action.yml Changes

The `action/setup/action.yml` currently outputs `matrix` and `resource_type`. It will change to output `lambda_matrix`, `step_function_matrix`, `api_gateway_matrix`, `has_lambdas`, `has_step_functions`, `has_api_gateways`. This is a breaking change to the action interface, but the workflow template is also changing, so they deploy together.

---

## Workflow Template Changes (No New Actions)

### Current: One Matrix, Three Conditional Jobs

```yaml
jobs:
  setup: ...
  deploy-lambda:
    if: needs.setup.outputs.resource_type == 'lambda'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
  deploy-step-function:
    if: needs.setup.outputs.resource_type == 'step_function'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
  deploy-api-gateway:
    if: needs.setup.outputs.resource_type == 'api_gateway'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
```

Problem: Only one job runs per dispatch. If all 3 types change, 3 separate workflow runs are triggered, each with 2 skipped jobs visible in GHA UI.

### New: Per-Type Matrices, All Jobs Conditional

```yaml
jobs:
  setup:
    outputs:
      lambda_matrix: ${{ steps.parse.outputs.lambda_matrix }}
      step_function_matrix: ${{ steps.parse.outputs.step_function_matrix }}
      api_gateway_matrix: ${{ steps.parse.outputs.api_gateway_matrix }}
      has_lambdas: ${{ steps.parse.outputs.has_lambdas }}
      has_step_functions: ${{ steps.parse.outputs.has_step_functions }}
      has_api_gateways: ${{ steps.parse.outputs.has_api_gateways }}
  deploy-lambda:
    if: needs.setup.outputs.has_lambdas == 'true'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
  deploy-step-function:
    if: needs.setup.outputs.has_step_functions == 'true'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.step_function_matrix) }}
  deploy-api-gateway:
    if: needs.setup.outputs.has_api_gateways == 'true'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.api_gateway_matrix) }}
```

Result: One workflow run per push. Only affected type jobs run. Skipped jobs show as "skipped" (grey) which is cleaner than separate workflow runs with skipped jobs. The `run-name` changes from showing `resource_type` to showing the deployment tag or commit info.

---

## Backend Dispatch Changes (No New Dependencies)

### Current: `trigger_dispatches()` -- One Dispatch Per Type

The function in `backend/src/ferry_backend/dispatch/trigger.py`:
1. Groups affected resources by type
2. Iterates over each type group
3. Builds a `DispatchPayload` per type
4. POSTs one `workflow_dispatch` per type

### New: `trigger_dispatch()` -- Single Batched Dispatch

The function will:
1. Build a `BatchedDispatchPayload` with all affected resources sorted into typed lists
2. POST one `workflow_dispatch` with the batched payload
3. No grouping loop needed -- just populate the three lists from the affected resources

This simplifies the dispatch logic. The `_build_resource()` helper and its per-type routing remain useful for populating the typed lists.

### Payload Size Check

Keep the existing `_MAX_PAYLOAD_SIZE = 65535` check. Apply it once to the single batched payload instead of per-type. If exceeded (astronomically unlikely), log an error and fall back to... nothing. There is no reasonable scenario where a ferry.yaml has enough resources to exceed this limit. The check is defensive only.

---

## What NOT to Add

| Temptation | Why Not |
|------------|---------|
| JSON compression (zlib/gzip + base64) | Payload fits easily within limits. Compression adds complexity for no benefit. |
| Multi-input splitting (spread payload across multiple `inputs` keys) | Single input works fine. Multiple inputs would require reassembly logic. |
| Artifact-based payload passing | Overkill. The payload is a few hundred to a few thousand characters. |
| `repository_dispatch` instead of `workflow_dispatch` | `workflow_dispatch` has explicit input schema and shows in GHA UI. `repository_dispatch` is less visible and has stricter payload limits (10 keys in `client_payload`). |
| New Python dependencies | Everything needed (Pydantic v2, structlog, json) already in the workspace. |
| Backward-compatible dual-version parsing | Backend and action deploy together from the same repo. No need to support v1 and v2 payloads simultaneously unless explicitly desired for rollback safety. |
| Dynamic job generation (reusable workflows, composite matrix) | GHA does not support dynamically generating jobs at runtime. The three deploy jobs must be statically defined in the workflow YAML. |

---

## Migration Strategy

Since Ferry deploys its own backend (push to main triggers ECR build + Lambda update) and the test repo's `ferry.yml` is a file the user controls:

1. **Backend + action changes land in one PR** (they are in the same monorepo)
2. **Test repo's `ferry.yml` must be updated** to reference new setup action outputs BEFORE the backend starts sending v2 payloads
3. **Deployment order:**
   a. Update test repo's `ferry.yml` with new template (references new outputs)
   b. Merge + deploy Ferry backend with batched dispatch
   c. Next push to test repo triggers batched dispatch through new workflow

This is the same deployment order used for v1.4 (unified workflow). No dual-version support needed if deployed in order.

---

## Summary: Changes by Package

| Package | What Changes | New Dependencies |
|---------|-------------|-----------------|
| `ferry-utils` (shared) | New `BatchedDispatchPayload` model, bump `SCHEMA_VERSION` to 2 | None |
| `ferry-backend` | `trigger.py`: replace per-type dispatch loop with single batched dispatch | None |
| `ferry-action` | `parse_payload.py`: output per-type matrices + boolean flags; `action/setup/action.yml`: new outputs | None |
| Workflow template (docs) | New `ferry.yml` template with per-type matrix references and boolean `if` guards | None |
| Test repo | Update `ferry.yml` to new template | None |

**Total new Python dependencies: 0**
**Total new GitHub Actions: 0**
**Total new infrastructure: 0**

## Sources

- [GitHub Docs: Events that trigger workflows - workflow_dispatch](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows) -- payload limit (65,535 chars), input count limit (25)
- [GitHub Community Discussion #27096](https://github.com/orgs/community/discussions/27096) -- empty matrix crash behavior and `if` guard workaround
- [GitHub Community Discussion #120093](https://github.com/orgs/community/discussions/120093) -- per-input value limits (1,024 for UI)
- [GitHub Blog Changelog 2025-12-04](https://github.blog/changelog/2025-12-04-actions-workflow-dispatch-workflows-now-support-25-inputs/) -- 25 input limit (up from 10)
- [Pydantic Issue #6884](https://github.com/pydantic/pydantic/issues/6884) -- discriminated union in list JSON schema issue (motivates separate typed lists)
- [GitHub Docs: Running variations of jobs in a workflow](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) -- dynamic matrix with fromJson
- Existing codebase: `ferry_utils/models/dispatch.py`, `ferry_backend/dispatch/trigger.py`, `ferry_action/parse_payload.py`, `action/setup/action.yml` -- analyzed directly
