# Phase 6: Fix Lambda function_name Pipeline - Research

**Researched:** 2026-02-27
**Domain:** Data pipeline wiring (Pydantic model -> dispatch payload -> GHA matrix -> deploy env var)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add `function_name` as a **new required field** on `LambdaResource`, alongside existing `name`
- `name` = resource key for identification in the dispatch payload; `function_name` = AWS Lambda target
- `function_name` is always a resolved `str` (never None) by the time it reaches `LambdaResource`
- `parse_payload.py` surfaces only `function_name` to the GHA matrix (as `INPUT_FUNCTION_NAME`); `name` is not passed to the action
- **Scope:** Only wire `function_name` -- do NOT add `runtime` to LambdaResource (Phase 7 handles runtime)
- Backend resolves defaults: `LambdaConfig`'s existing `model_validator` defaults `function_name` to `name`
- `_build_resource` in `trigger.py` reads the already-resolved `function_name` from `LambdaConfig`
- No validation of AWS Lambda naming rules on `function_name` -- let AWS reject invalid names at deploy time
- Single source of truth: backend resolves, action trusts the value
- **Missing function_name:** `deploy.py` fails fast with clear message if `INPUT_FUNCTION_NAME` is missing or empty -- no fallback, no guessing
- **Function not found:** Error message includes the function_name that was tried AND suggests possible cause: "Lambda function 'X' not found. Check ferry.yaml function_name or verify the Lambda exists in the target account."

### Claude's Discretion
- Test structure and assertion patterns
- Exact error message wording (following the patterns above)
- Whether to add function_name to existing test fixtures or create new ones

### Deferred Ideas (OUT OF SCOPE)
- Wiring `runtime` through the same pipeline path -- Phase 7 (tech debt cleanup)
- AWS naming validation on function_name -- future enhancement if user demand
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPLOY-01 | Ferry Action deploys Lambda functions (update-function-code, wait for LastUpdateStatus: Successful, publish version, update alias) | `deploy.py` already implements the full deploy sequence correctly. The gap is that `function_name` never reaches it through the dispatch pipeline. This phase wires the field through 3 intermediate files (dispatch model, trigger builder, parse_payload matrix) so deploy.py receives it as `INPUT_FUNCTION_NAME`. |
</phase_requirements>

## Summary

This phase closes a well-characterized integration break where `function_name` exists at both endpoints (LambdaConfig in the backend, deploy.py in the action) but is dropped in the dispatch pipeline that connects them. The audit identified the exact break: `_build_resource` in `trigger.py` constructs `LambdaResource` without `function_name`, the dispatch model `LambdaResource` has no such field, and `parse_payload.py` never includes it in the GHA matrix output.

The fix is surgical: add `function_name: str` to `LambdaResource` in the shared dispatch model, pass `function_name=lam.function_name` in `_build_resource`, include `"function_name": r.function_name` in the lambda matrix builder, and update `deploy.py` error handling for better error messages when the function is not found. No new libraries, patterns, or architectural changes are needed. All existing test infrastructure is sufficient.

**Primary recommendation:** Wire `function_name` through the 4 touch points (dispatch model, trigger builder, parse_payload matrix, deploy.py error messages) and update all affected tests to include the field. This is a data-plumbing fix, not a design change.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic v2 | 2.x | Frozen model with `function_name: str` field | Already used for all dispatch models; ConfigDict(frozen=True) convention |
| pytest | 8.x | Test framework | Already used across all 237 existing tests |
| moto | 5.x | AWS Lambda mocking for deploy tests | Already used in test_deploy.py |
| httpx_mock | - | HTTP mock for GitHub API dispatch tests | Already used in test_dispatch_trigger.py |

### Supporting
No new libraries needed. This phase uses exclusively existing project dependencies.

### Alternatives Considered
None. The stack is fully established. This is a plumbing fix within the existing codebase.

## Architecture Patterns

### Recommended Project Structure
No new files needed. Changes touch exactly these existing files:

```
utils/src/ferry_utils/models/dispatch.py     # Add function_name to LambdaResource
backend/src/ferry_backend/dispatch/trigger.py # Pass function_name in _build_resource
action/src/ferry_action/parse_payload.py      # Include function_name in lambda matrix
action/src/ferry_action/deploy.py             # Improve error message for ResourceNotFoundException
tests/test_utils/test_dispatch_models.py      # Update LambdaResource tests
tests/test_backend/test_dispatch_trigger.py   # Update trigger tests to verify function_name flows
tests/test_action/test_parse_payload.py       # Update matrix tests to verify function_name in output
tests/test_action/test_deploy.py              # Update deploy main() tests for error handling
```

### Pattern 1: Frozen Pydantic Model Field Addition
**What:** Adding a required field to an existing frozen Pydantic model
**When to use:** When extending a shared data contract
**Example:**
```python
# Current LambdaResource (dispatch.py line 15-23)
class LambdaResource(BaseModel):
    model_config = ConfigDict(frozen=True)
    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str

# After: Add function_name as required str
class LambdaResource(BaseModel):
    model_config = ConfigDict(frozen=True)
    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str
    function_name: str
```
**Key detail:** `function_name` is `str` (not `str | None`) because the backend resolves the default before constructing `LambdaResource`. By the time it reaches the dispatch model, it is always a resolved string.

### Pattern 2: Config-to-Dispatch Field Mapping in _build_resource
**What:** Passing config fields through to dispatch resource constructors
**When to use:** When a config field needs to reach the action via dispatch payload
**Example:**
```python
# Current (trigger.py line 69-72)
if resource_type == "lambda":
    for lam in config.lambdas:
        if lam.name == name:
            return LambdaResource(name=name, source=lam.source_dir, ecr=lam.ecr_repo)

# After: Include function_name
if resource_type == "lambda":
    for lam in config.lambdas:
        if lam.name == name:
            return LambdaResource(
                name=name,
                source=lam.source_dir,
                ecr=lam.ecr_repo,
                function_name=lam.function_name,
            )
```
**Key detail:** `lam.function_name` is already resolved by `LambdaConfig`'s `model_validator` (defaults to `name` if not explicitly set). No additional resolution logic needed in `_build_resource`.

### Pattern 3: Matrix Field Surfacing in parse_payload
**What:** Including a dispatch resource field in the GHA matrix output
**When to use:** When the deploy action needs a value from the dispatch payload
**Example:**
```python
# Current _build_lambda_matrix (parse_payload.py line 23-43)
return [
    {
        "name": r.name,
        "source": r.source,
        "ecr": r.ecr,
        "trigger_sha": payload.trigger_sha,
        "deployment_tag": payload.deployment_tag,
        "runtime": "python3.12",
    }
    for r in payload.resources
    if isinstance(r, LambdaResource)
]

# After: Add function_name
return [
    {
        "name": r.name,
        "source": r.source,
        "ecr": r.ecr,
        "function_name": r.function_name,
        "trigger_sha": payload.trigger_sha,
        "deployment_tag": payload.deployment_tag,
        "runtime": "python3.12",
    }
    for r in payload.resources
    if isinstance(r, LambdaResource)
]
```
**Key detail:** The matrix `function_name` key maps to `${{ matrix.function_name }}` in the user's workflow YAML, which gets passed to the deploy action's `function-name` input, which becomes `INPUT_FUNCTION_NAME` env var in deploy.py.

### Pattern 4: deploy.py Error Handling Enhancement
**What:** Improving error messages for function-not-found scenarios
**When to use:** When the error message should help users diagnose ferry.yaml misconfiguration
**Example:**
```python
# Current ResourceNotFoundException hint (deploy.py line 219)
"ResourceNotFoundException": (
    f"Lambda function '{function_name}' not found"
),

# After: More helpful error message per CONTEXT.md decision
"ResourceNotFoundException": (
    f"Lambda function '{function_name}' not found. "
    f"Check ferry.yaml function_name or verify the "
    f"Lambda exists in the target account."
),
```

### Anti-Patterns to Avoid
- **Adding function_name as Optional on LambdaResource:** The CONTEXT.md decision locks this as a required `str`. The backend resolves defaults; the dispatch model trusts the resolved value.
- **Adding default resolution logic in parse_payload.py:** The backend is the single source of truth for defaults. The action should never derive `function_name` from `name` -- it receives an already-resolved value.
- **Passing `name` to the GHA matrix as INPUT_RESOURCE_NAME interchangeably with `function_name`:** These are distinct: `name` is the ferry.yaml resource key for identification; `function_name` is the AWS Lambda function name. deploy.py already correctly reads both `INPUT_RESOURCE_NAME` (for logging) and `INPUT_FUNCTION_NAME` (for AWS API calls).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Default resolution of function_name | Fallback logic in parse_payload or deploy.py | LambdaConfig's existing model_validator | Single source of truth; backend resolves, action trusts |
| Pydantic model serialization | Custom JSON builders | model_dump_json() / model_validate_json() | Already used in trigger_dispatches and build_matrix |

**Key insight:** This phase has no hand-roll risks. The entire fix is wiring an existing value through existing infrastructure. No new abstractions or custom logic needed.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests with New Required Field
**What goes wrong:** Adding `function_name: str` to `LambdaResource` makes it a required field. Every existing test that constructs a `LambdaResource` without `function_name` will fail with ValidationError.
**Why it happens:** 14+ test locations construct LambdaResource with only `name`, `source`, `ecr`.
**How to avoid:** Update ALL test sites that construct LambdaResource to include `function_name`. Grep for `LambdaResource(` across the test directory.
**Warning signs:** pytest failures mentioning `function_name` as missing required field.

Affected test files (identified by code search):
- `tests/test_utils/test_dispatch_models.py` -- 7 LambdaResource constructions
- `tests/test_backend/test_dispatch_trigger.py` -- all lambda config/dispatch tests
- `tests/test_action/test_parse_payload.py` -- `_make_payload` helper and individual tests

### Pitfall 2: Forgetting to Update _make_payload Test Helper
**What goes wrong:** The `_make_payload()` helper in `test_parse_payload.py` builds raw JSON dicts for LambdaResource. If `function_name` is required but missing from these dicts, Pydantic validation will fail during test setup, not during the test assertion.
**Why it happens:** `_make_payload` uses raw dicts, not Pydantic model constructors, so the failure happens at `DispatchPayload.model_validate_json()` inside `build_matrix()`.
**How to avoid:** Add `"function_name": "order-processor"` (or matching the `name` value) to all lambda resource dicts in `_make_payload` and individual test helpers.
**Warning signs:** Tests failing with ValidationError about `function_name` missing, rather than the intended assertion.

### Pitfall 3: Serialization/Deserialization Round-Trip
**What goes wrong:** Adding a field to the Pydantic model but not updating the JSON construction in trigger.py means the field serializes to JSON correctly from tests but is missing from real payloads constructed by `_build_resource`.
**Why it happens:** Tests might pass if they construct LambdaResource directly with function_name, but the real pipeline builds LambdaResource via `_build_resource` which currently omits function_name.
**How to avoid:** The trigger.py `_build_resource` change MUST be included. Verify with the existing `test_trigger_dispatches_payload_format` test that checks the actual serialized payload.
**Warning signs:** Tests pass but function_name is missing from the actual workflow_dispatch payload in production.

### Pitfall 4: Inconsistent name/function_name Values in Tests
**What goes wrong:** Tests use `function_name=name` (the default case) but never test the case where function_name differs from name.
**Why it happens:** The default-to-name behavior in LambdaConfig makes it easy to overlook the explicit override case.
**How to avoid:** Include at least one test case where `function_name` is explicitly different from `name` (e.g., `name="order"` but `function_name="order-processor-prod"`). This verifies the field is actually being passed through, not just accidentally matching `name`.
**Warning signs:** Tests pass but function_name is actually just `name` everywhere, masking a wiring bug.

## Code Examples

### Full Pipeline Data Flow (Before and After)

**Before (BROKEN):**
```
ferry.yaml:
  lambdas:
    - name: order
      source_dir: services/order
      ecr_repo: ferry/order
      function_name: order-processor-prod  # <-- user sets explicit function_name

LambdaConfig:      function_name = "order-processor-prod" (resolved by model_validator)
_build_resource:   LambdaResource(name="order", source="services/order", ecr="ferry/order")
                   # function_name DROPPED here
DispatchPayload:   {"resources": [{"name": "order", "source": "...", "ecr": "..."}]}
parse_payload:     matrix: {"name": "order", "source": "...", "ecr": "...", ...}
                   # No function_name in matrix
deploy action.yml: INPUT_FUNCTION_NAME = ${{ inputs.function-name }}  # NOT SET by matrix
deploy.py:         os.environ["INPUT_FUNCTION_NAME"]  # KeyError!
```

**After (FIXED):**
```
ferry.yaml:
  lambdas:
    - name: order
      source_dir: services/order
      ecr_repo: ferry/order
      function_name: order-processor-prod

LambdaConfig:      function_name = "order-processor-prod"
_build_resource:   LambdaResource(name="order", source="...", ecr="...", function_name="order-processor-prod")
DispatchPayload:   {"resources": [{"name": "order", ..., "function_name": "order-processor-prod"}]}
parse_payload:     matrix: {"name": "order", ..., "function_name": "order-processor-prod", ...}
deploy action.yml: INPUT_FUNCTION_NAME = ${{ inputs.function-name }}  # Set from matrix.function_name
deploy.py:         os.environ["INPUT_FUNCTION_NAME"] = "order-processor-prod"  # Success!
```

### Test Pattern: Verifying function_name Flows Through Dispatch
```python
# In test_dispatch_trigger.py -- verify function_name in serialized payload
def test_trigger_dispatches_includes_function_name(self, httpx_mock):
    httpx_mock.add_response(url=..., status_code=204)
    config = self._make_config(
        lambdas=[
            LambdaConfig(
                name="order",
                source_dir="services/order",
                ecr_repo="ferry/order",
                function_name="order-prod",  # Explicit, different from name
            ),
        ],
    )
    affected = [self._make_affected("order")]
    client = GitHubClient()
    trigger_dispatches(client, "owner/repo", config, affected, "sha123", "main-sha123", "")

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    payload_data = json.loads(body["inputs"]["payload"])
    resource = payload_data["resources"][0]
    assert resource["function_name"] == "order-prod"  # Not "order"
```

### Test Pattern: Verifying function_name in GHA Matrix Output
```python
# In test_parse_payload.py -- verify function_name appears in matrix
def test_lambda_matrix_includes_function_name(self) -> None:
    resources = [
        {
            "resource_type": "lambda",
            "name": "order",
            "source": "services/order",
            "ecr": "ferry/order",
            "function_name": "order-prod",
        },
    ]
    payload_str = _make_payload(resources=resources)
    result = build_matrix(payload_str)
    entry = result["include"][0]
    assert entry["function_name"] == "order-prod"
```

## State of the Art

Not applicable -- this phase is a bug fix within existing codebase patterns, not adoption of new technology.

## Open Questions

None. The gap is fully characterized by the audit report, all 4 touch points are identified, the CONTEXT.md decisions lock all design choices, and the existing codebase patterns provide clear examples for every change.

## Sources

### Primary (HIGH confidence)
- **Codebase inspection** -- direct reading of all 8 affected files (4 source + 4 test files)
- **Audit report** (`.planning/v1.0-MILESTONE-AUDIT.md`) -- exact characterization of the DEPLOY-01 gap, broken data path, and 3-file fix
- **Existing test suite** -- 237 passing tests confirm current patterns; test patterns verified by reading test files

### Secondary (MEDIUM confidence)
None needed -- this is purely internal codebase wiring with no external dependencies.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries; all changes within existing Pydantic/pytest/moto patterns
- Architecture: HIGH -- the data flow is fully traced from ferry.yaml to deploy.py; exact line numbers identified
- Pitfalls: HIGH -- all pitfalls are concrete (test breakage from required field addition) with specific file/line references

**Research date:** 2026-02-27
**Valid until:** Indefinite (internal codebase analysis, no external dependencies)
