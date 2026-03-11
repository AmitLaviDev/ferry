# Phase 26: Backend Batched Dispatch - Research

**Researched:** 2026-03-11
**Domain:** Python backend dispatch logic (Pydantic v2, httpx, structlog)
**Confidence:** HIGH

## Summary

Phase 26 replaces the per-type dispatch loop in `trigger.py` with a single batched dispatch using the `BatchedDispatchPayload` (v2) model added in Phase 25. The change is confined to a single file (`backend/src/ferry_backend/dispatch/trigger.py`) and its corresponding test file. The handler (`handler.py`) requires zero changes because the return value contract (`list[dict]`) is stable.

The core transformation is straightforward: instead of iterating over grouped resource types and dispatching one `DispatchPayload` per type, the new code builds a single `BatchedDispatchPayload` containing all types, serializes it, checks the size, and either dispatches it (happy path) or falls back to per-type v1 dispatch (oversized payload). The existing `_build_resource()` helper is reusable as-is.

**Primary recommendation:** Extract the current per-type loop into `_dispatch_per_type()`, then write the new batched path as the main body of `trigger_dispatches()`. This keeps the fallback path identical to proven v1 behavior while making the default path use v2.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Fallback behavior on payload-size exceeded**
   - Client-side size check only (`len(payload_json) > 65535`) -- no server-side retry
   - On fallback: log a structured warning (`dispatch_fallback_to_per_type` with payload size), then dispatch per-type v1 payloads
   - Fallback is explicit in logs but NOT in the return value -- return shape stays the same as normal per-type results
   - Fallback uses actual v1 `DispatchPayload` wire format (not v2 single-type batched payloads) -- proven, action already handles it
   - Extract v1 per-type loop into a `_dispatch_per_type()` helper; main function body is the v2 batched path

2. **Return value / caller contract**
   - Return shape is unchanged: `list[dict]` with one entry per resource type, each `{"type": str, "status": int, "workflow": str}`
   - Batched dispatch: expand into one entry per type included in the batch (all share the same status code from the single API call)
   - Fallback dispatch: normal per-type entries (identical to v1 behavior)
   - Handler (`handler.py`) requires zero changes -- return shape is stable across both paths
   - Logging: one `dispatch_triggered` log event per type included, with `mode="batched"` field added

3. **Backward compatibility / rollout**
   - No toggle, no feature flag, no env var -- ship v2 as the only path
   - No rollout concerns -- test repo is the only consumer, project is unpublished
   - Deploy backend and action together (Phases 26+27 go live at same time via Phase 28 E2E)
   - v1 `DispatchPayload` model kept as-is in ferry-utils (used by fallback path + action parsing)
   - v1 per-type dispatch path exists solely as the >65KB payload-size fallback

### Deferred Ideas (OUT OF SCOPE)
None captured during discussion.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISP-01 | Backend sends a single workflow_dispatch per push containing all affected resource types in one payload | New `trigger_dispatches()` builds `BatchedDispatchPayload` with all types, makes one API call |
| DISP-03 | Backend falls back to per-type dispatch if combined payload exceeds 65,535 character limit | Size check on serialized JSON; if exceeded, calls `_dispatch_per_type()` helper with v1 `DispatchPayload` per type |

</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic v2 | >=2.0 | `BatchedDispatchPayload` model serialization | Already used for v1 `DispatchPayload`; `model_dump_json()` for size check |
| httpx | latest | GitHub API POST for workflow_dispatch | Already used via `GitHubClient.post()` |
| structlog | latest | Structured logging for dispatch events | Already used throughout backend |
| pytest | >=8.0 | Test framework | Already configured in pyproject.toml |
| pytest-httpx | >=0.30 | Mock httpx requests in dispatch tests | Already used in `test_dispatch_trigger.py` |

### Supporting
No new libraries needed. Phase 26 uses only existing dependencies.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `len(payload_json)` size check | `sys.getsizeof()` | `len()` measures character count which matches GitHub's limit; `sys.getsizeof()` measures Python object memory, irrelevant here |

**Installation:** No new packages required.

## Architecture Patterns

### Files Modified
```
backend/src/ferry_backend/dispatch/trigger.py  # Main change
tests/test_backend/test_dispatch_trigger.py     # Updated tests
```

### Files Unchanged (confirmed)
```
backend/src/ferry_backend/webhook/handler.py    # Zero changes
utils/src/ferry_utils/models/dispatch.py        # Phase 25 (done)
utils/src/ferry_utils/constants.py              # Phase 25 (done)
```

### Pattern 1: Extract-then-Replace Refactor

**What:** Extract the existing per-type loop into a private helper `_dispatch_per_type()`, then write the new batched dispatch as the main path in `trigger_dispatches()`.

**When to use:** When the old behavior must be preserved as a fallback while introducing new primary behavior.

**Why this pattern:** The existing per-type loop is proven in production (v1.0-v1.4). Extracting it wholesale into a helper means the fallback path is byte-for-byte identical to the working v1 code, eliminating risk of regression.

**Structure:**
```python
def _dispatch_per_type(
    client: GitHubClient,
    repo: str,
    grouped: dict[str, list[AffectedResource]],
    config: FerryConfig,
    sha: str,
    deployment_tag: str,
    pr_number: str,
    default_branch: str,
) -> list[dict]:
    """Per-type dispatch (v1 behavior). Used as fallback for oversized batched payloads."""
    # ... existing per-type loop (lines 141-182 of current trigger.py)


def trigger_dispatches(...) -> list[dict]:
    """Fire workflow_dispatch for affected resources.

    Default: single batched dispatch (v2).
    Fallback: per-type dispatch (v1) if payload exceeds 65KB.
    """
    # 1. Group by type (same as current)
    # 2. Build typed resource lists for BatchedDispatchPayload
    # 3. Serialize, check size
    # 4. If fits: single dispatch, expand results
    # 5. If too big: log warning, call _dispatch_per_type()
```

### Pattern 2: Resource Type Mapping (singular -> plural)

**What:** The `AffectedResource.resource_type` uses singular form ("lambda", "step_function", "api_gateway") while `BatchedDispatchPayload` uses plural field names ("lambdas", "step_functions", "api_gateways"). The implementation must map between these.

**Critical mapping:**
```python
# AffectedResource.resource_type -> BatchedDispatchPayload field name
_TYPE_TO_FIELD = {
    "lambda": "lambdas",
    "step_function": "step_functions",
    "api_gateway": "api_gateways",
}
```

**How to use:** When building the `BatchedDispatchPayload`, iterate over grouped resources and assign to the correct field by name. This can be done with a dict comprehension that maps grouped keys to keyword arguments:

```python
# Build typed resource lists
typed_resources: dict[str, list] = {"lambdas": [], "step_functions": [], "api_gateways": []}
for rtype, resources in grouped.items():
    field_name = _TYPE_TO_FIELD[rtype]
    typed_resources[field_name] = [_build_resource(rtype, r.name, config) for r in resources]

payload = BatchedDispatchPayload(
    **typed_resources,
    trigger_sha=sha,
    deployment_tag=deployment_tag,
    pr_number=pr_number,
)
```

### Pattern 3: Result Expansion for Batched Dispatch

**What:** The return contract is `list[dict]` with one entry per resource type. For batched dispatch (one API call), expand the single response into one entry per type:

```python
# Single API call returns one status code
status = resp.status_code
for rtype in grouped:
    results.append({"type": rtype, "status": status, "workflow": workflow_file})
```

This maintains the handler's expectation of per-type results while using a single dispatch call.

### Anti-Patterns to Avoid
- **Modifying handler.py:** The return contract is stable. No changes needed.
- **Building v2 payloads in the fallback path:** Fallback MUST use actual v1 `DispatchPayload` objects, not single-type batched payloads. The action already parses v1 payloads.
- **Storing typed_resources as lists of AffectedResource:** The `BatchedDispatchPayload` expects typed model instances (`LambdaResource`, `StepFunctionResource`, etc.), not `AffectedResource` dataclass instances. Must call `_build_resource()` for each.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Payload serialization | Manual JSON building | `BatchedDispatchPayload.model_dump_json()` | Pydantic handles discriminated union serialization correctly |
| Size measurement | Character counting on dict | `len(payload.model_dump_json())` | Must measure the exact JSON string that will be sent |
| Resource type mapping | If/elif chains for plural/singular | `_TYPE_TO_FIELD` dict lookup | Single source of truth, extensible |

**Key insight:** The `BatchedDispatchPayload` model already handles all the type-safe serialization. The implementation just needs to populate it correctly and check the size.

## Common Pitfalls

### Pitfall 1: Resource Type Naming Mismatch
**What goes wrong:** Using `AffectedResource.resource_type` ("lambda") directly as a `BatchedDispatchPayload` field name fails because the model uses plural forms ("lambdas").
**Why it happens:** Two different naming conventions exist in the codebase -- `_SECTION_TYPE_MAP` in `changes.py` maps plural config sections to singular type strings.
**How to avoid:** Explicit `_TYPE_TO_FIELD` mapping dict. Never assume field names match resource_type strings.
**Warning signs:** `TypeError` or `unexpected keyword argument` when constructing `BatchedDispatchPayload`.

### Pitfall 2: Size Check on Wrong Representation
**What goes wrong:** Checking `len(json.dumps(payload.model_dump()))` instead of `len(payload.model_dump_json())` could give different results due to Pydantic's JSON serialization settings.
**Why it happens:** Pydantic `model_dump_json()` may serialize differently than `json.dumps(model_dump())` in edge cases.
**How to avoid:** Use `model_dump_json()` consistently for both size check AND the value sent in `{"inputs": {"payload": ...}}`. Store the serialized string once, use it for both.
**Warning signs:** Payload accepted by size check but rejected by GitHub (or vice versa).

### Pitfall 3: Test Assertion Count Regression
**What goes wrong:** Existing tests like `test_trigger_dispatches_multiple_types` expect 2 HTTP requests (one per type). After batched dispatch, the same test scenario produces 1 HTTP request.
**Why it happens:** The core behavioral change IS reducing API calls. Tests must be updated to match.
**How to avoid:** Update tests explicitly -- the "2 types -> 2 dispatches" test becomes "2 types -> 1 dispatch with batched payload". Add new tests for fallback path.
**Warning signs:** Tests fail with "Expected 2 requests, got 1."

### Pitfall 4: Forgetting mode Field in Logging
**What goes wrong:** Log events don't distinguish batched from per-type dispatch, making debugging harder.
**Why it happens:** Easy to forget the `mode="batched"` or `mode="per_type"` field on log events.
**How to avoid:** CONTEXT.md explicitly requires `mode="batched"` on `dispatch_triggered` log events. Add to both code paths.
**Warning signs:** Log output lacks dispatch mode context during E2E debugging (Phase 28).

### Pitfall 5: Fallback Path Not Getting v1 Payload Size Check
**What goes wrong:** The fallback `_dispatch_per_type()` helper should still check per-type v1 payload sizes (the existing `_MAX_PAYLOAD_SIZE` check per type). If a single resource type's v1 payload exceeds 65KB, it should return 413 just like today.
**Why it happens:** When extracting the per-type loop, it's easy to strip out the size check.
**How to avoid:** Extract the ENTIRE per-type loop including the size check into `_dispatch_per_type()`.
**Warning signs:** Oversized single-type payloads silently succeed instead of returning 413.

## Code Examples

### Current trigger.py Structure (lines 103-184)
The existing `trigger_dispatches()` function:
1. Groups affected resources by `resource_type`
2. Iterates per type, builds `DispatchPayload` (v1)
3. Serializes, checks size, dispatches
4. Returns `list[dict]` results

Source: `/Users/amit/Repos/github/ferry/backend/src/ferry_backend/dispatch/trigger.py`

### New Imports Needed
```python
from ferry_utils.constants import BATCHED_SCHEMA_VERSION, WORKFLOW_FILENAME
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
    BatchedDispatchPayload,
    DispatchPayload,
    LambdaResource,
    StepFunctionResource,
)
```

Note: `BATCHED_SCHEMA_VERSION` import is not strictly required since it's embedded in the model default, but importing it signals intent and can be useful for logging.

### Type-to-Field Mapping
```python
# Maps AffectedResource.resource_type -> BatchedDispatchPayload field name
_TYPE_TO_FIELD: dict[str, str] = {
    "lambda": "lambdas",
    "step_function": "step_functions",
    "api_gateway": "api_gateways",
}
```

### Building the Batched Payload
```python
# Group by resource type (same as current code)
grouped: dict[str, list[AffectedResource]] = {}
for resource in affected:
    grouped.setdefault(resource.resource_type, []).append(resource)

# Build typed dispatch resource lists
typed_resources: dict[str, list] = {}
for rtype, resources in grouped.items():
    field_name = _TYPE_TO_FIELD[rtype]
    typed_resources[field_name] = [
        _build_resource(rtype, r.name, config) for r in resources
    ]

payload = BatchedDispatchPayload(
    **typed_resources,
    trigger_sha=sha,
    deployment_tag=deployment_tag,
    pr_number=pr_number,
)
```

### Size Check and Dispatch/Fallback
```python
payload_json = payload.model_dump_json()

if len(payload_json) > _MAX_PAYLOAD_SIZE:
    logger.warning(
        "dispatch_fallback_to_per_type",
        payload_size=len(payload_json),
        max_size=_MAX_PAYLOAD_SIZE,
        type_count=len(grouped),
    )
    return _dispatch_per_type(
        client, repo, grouped, config, sha, deployment_tag,
        pr_number, default_branch,
    )

# Single batched dispatch
workflow_file = WORKFLOW_FILENAME
resp = client.post(
    f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
    json={"ref": default_branch, "inputs": {"payload": payload_json}},
)

# Expand single result into per-type entries
results: list[dict] = []
for rtype in grouped:
    logger.info(
        "dispatch_triggered",
        resource_type=rtype,
        workflow=workflow_file,
        resource_count=len(grouped[rtype]),
        status=resp.status_code,
        mode="batched",
    )
    results.append({"type": rtype, "status": resp.status_code, "workflow": workflow_file})

return results
```

### Test Pattern: Verifying Batched Payload
```python
def test_trigger_dispatches_multiple_types_batched(self, httpx_mock):
    """Lambda + step_function -> ONE dispatch with batched payload."""
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches",
        status_code=204,
    )
    # ... setup config and affected ...
    results = trigger_dispatches(client, "owner/repo", config, affected, ...)

    # Only 1 API call (not 2)
    assert len(httpx_mock.get_requests()) == 1

    # Results still have one entry per type
    assert len(results) == 2
    types = {r["type"] for r in results}
    assert types == {"lambda", "step_function"}

    # Verify batched payload structure
    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
    assert payload.v == 2
    assert len(payload.lambdas) == 1
    assert len(payload.step_functions) == 1
```

### Test Pattern: Verifying Fallback
```python
def test_trigger_dispatches_fallback_on_oversized(self, httpx_mock, monkeypatch):
    """Oversized batched payload falls back to per-type dispatch."""
    # Mock the size limit to trigger fallback easily
    monkeypatch.setattr("ferry_backend.dispatch.trigger._MAX_PAYLOAD_SIZE", 10)
    httpx_mock.add_response(status_code=204)
    httpx_mock.add_response(status_code=204)
    # ... setup 2 types ...
    results = trigger_dispatches(...)

    # 2 API calls (per-type fallback)
    assert len(httpx_mock.get_requests()) == 2

    # Each uses v1 DispatchPayload
    for req in httpx_mock.get_requests():
        body = json.loads(req.content)
        payload = json.loads(body["inputs"]["payload"])
        assert payload["v"] == 1
```

## State of the Art

| Old Approach (v1, current) | New Approach (v2, this phase) | When Changed | Impact |
|---------------------------|-------------------------------|--------------|--------|
| One `DispatchPayload` per resource type | One `BatchedDispatchPayload` per push | Phase 26 | Reduces N workflow runs to 1 per push |
| Per-type loop in `trigger_dispatches()` | Batched path + `_dispatch_per_type()` fallback | Phase 26 | Cleaner GHA UI, same reliability |

**Not changing:**
- `_build_resource()` helper -- reusable as-is
- `build_deployment_tag()` -- unchanged
- `handler.py` -- zero modifications
- Return contract `list[dict]` -- stable

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 + pytest-httpx >=0.30 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_backend/test_dispatch_trigger.py -v` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISP-01 | Multi-type push produces single dispatch | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_multiple_types_batched -x` | No -- Wave 0 |
| DISP-01 | Single-type push produces single dispatch with batched payload | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_single_type_batched -x` | No -- Wave 0 |
| DISP-01 | Batched payload contains correct v=2 and typed resource lists | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_batched_payload_format -x` | No -- Wave 0 |
| DISP-03 | Oversized payload falls back to per-type v1 dispatch | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_fallback_on_oversized -x` | No -- Wave 0 |
| DISP-03 | Fallback uses v1 DispatchPayload wire format | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_fallback_uses_v1_payload -x` | No -- Wave 0 |
| DISP-01 | Empty affected list produces no API calls | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_empty -x` | Yes -- existing |
| DISP-01 | Return shape is list[dict] with type/status/workflow per type | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_return_shape -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_backend/test_dispatch_trigger.py -v`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update existing tests in `tests/test_backend/test_dispatch_trigger.py` to expect batched behavior (single API call for multi-type)
- [ ] Add new tests for: batched payload format verification, fallback on oversized payload, fallback uses v1 format, mode field in logging
- [ ] No framework install needed -- pytest and pytest-httpx already configured

## Open Questions

1. **Logging assertion in tests**
   - What we know: CONTEXT.md requires `mode="batched"` in dispatch_triggered log events
   - What's unclear: Whether tests should assert on structlog output or just verify behavior
   - Recommendation: Focus tests on HTTP request count and payload format (observable behavior). Log assertions are nice-to-have but not blocking. If desired, use `structlog.testing.capture_logs()`.

2. **All-three-types test fixture**
   - What we know: Existing tests cover lambda+SF, lambda-only, empty. No test covers all 3 types.
   - What's unclear: Whether an all-3-types test is needed for Phase 26 or deferred to Phase 28 E2E
   - Recommendation: Add an all-3-types unit test in Phase 26. It's cheap to write and validates the full batched payload structure.

## Sources

### Primary (HIGH confidence)
- `/Users/amit/Repos/github/ferry/backend/src/ferry_backend/dispatch/trigger.py` -- current dispatch implementation (184 lines)
- `/Users/amit/Repos/github/ferry/utils/src/ferry_utils/models/dispatch.py` -- BatchedDispatchPayload model (Phase 25, already implemented)
- `/Users/amit/Repos/github/ferry/utils/src/ferry_utils/constants.py` -- BATCHED_SCHEMA_VERSION = 2
- `/Users/amit/Repos/github/ferry/tests/test_backend/test_dispatch_trigger.py` -- existing 11 tests (all passing)
- `/Users/amit/Repos/github/ferry/backend/src/ferry_backend/detect/changes.py` -- AffectedResource dataclass and _SECTION_TYPE_MAP
- `/Users/amit/Repos/github/ferry/.planning/phases/26-backend-batched-dispatch/26-CONTEXT.md` -- locked decisions

### Secondary (MEDIUM confidence)
- [GitHub community discussion on workflow_dispatch limits](https://github.com/orgs/community/discussions/120093) -- 65,535 character limit confirmed by community consensus
- [GitHub Actions input limit increase](https://github.blog/changelog/2025-12-04-actions-workflow-dispatch-workflows-now-support-25-inputs/) -- 25 inputs now supported (not relevant to this phase, but good context)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing dependencies
- Architecture: HIGH -- single-file change, clear extract-then-replace pattern, CONTEXT.md prescribes exact approach
- Pitfalls: HIGH -- identified 5 specific pitfalls from code analysis, all have concrete prevention strategies

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable -- internal project, no external API changes expected)
