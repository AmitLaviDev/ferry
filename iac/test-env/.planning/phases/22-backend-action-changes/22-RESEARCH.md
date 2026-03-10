# Phase 22: Backend and Action Code Changes - Research

**Researched:** 2026-03-10
**Domain:** Python backend refactor + GitHub Actions composite action output
**Confidence:** HIGH

## Summary

Phase 22 is a surgical code refactor across four files in the Ferry monorepo. The backend currently maps each resource type to a per-type workflow filename (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) using `RESOURCE_TYPE_WORKFLOW_MAP` in `constants.py`. This phase replaces that dict with a single `WORKFLOW_FILENAME = "ferry.yml"` constant and simplifies `trigger.py` to use it directly. Simultaneously, the setup composite action gains a new `resource_type` output so the unified workflow (Phase 23) can route dispatches to the correct deploy job.

All four source files have been read and analyzed. The changes are minimal and well-bounded: 2 files in the backend (`constants.py`, `trigger.py`), 2 files in the action (`parse_payload.py`, `setup/action.yml`). The test impact is concentrated in `test_dispatch_trigger.py` (6 tests with hardcoded old workflow filenames in URL mocks and assertions) and `test_handler_phase2.py` (1 helper function with a default parameter). No tests need to be added for `parse_payload.py` -- the new `resource_type` output will be verified by adding assertions to the existing `TestMain::test_valid_payload_writes_output` test.

**Primary recommendation:** Make all changes atomically in a single commit. The test suite will break if constants are changed without updating test assertions simultaneously.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BE-01 | All dispatches target `ferry.yml` regardless of resource type | `trigger.py` lines 153-155 currently derive filename from `RESOURCE_TYPE_WORKFLOW_MAP`. Replace with `WORKFLOW_FILENAME` constant. See "Source File: trigger.py" section. |
| BE-02 | Remove/replace `RESOURCE_TYPE_WORKFLOW_MAP` with single workflow filename constant | `constants.py` lines 17-22 define the map. Remove it, add `WORKFLOW_FILENAME = "ferry.yml"`. See "Source File: constants.py" section. |
| ACT-01 | Setup action exposes `resource_type` as a workflow output | `setup/action.yml` currently has only `matrix` output. Add `resource_type` output mapped to `steps.parse.outputs.resource_type`. See "Source File: setup/action.yml" section. |
| ACT-02 | Setup action outputs matrix JSON (existing behavior preserved) | No change needed to matrix logic. `build_matrix()` in `parse_payload.py` is untouched. Verified by existing 17 tests in `test_parse_payload.py`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14 | Backend + action runtime | Already in use, no change |
| Pydantic v2 | latest | DispatchPayload model | `resource_type` field already exists in payload, no schema change |
| pytest | >=8.0 | Test framework | Already configured in pyproject.toml |
| pytest-httpx | >=0.30 | HTTP mock for dispatch tests | Already in use for mocking GitHub API calls |

### Supporting
No new libraries needed. This is a pure refactor of existing code.

### Alternatives Considered
None. The changes are prescribed by the requirements -- there is no design ambiguity.

## Architecture Patterns

### Current Architecture (Before)

```
constants.py:
  RESOURCE_TYPE_WORKFLOW_MAP = {
      ResourceType.LAMBDA: "lambdas",
      ResourceType.STEP_FUNCTION: "step_functions",
      ResourceType.API_GATEWAY: "api_gateways",
  }

trigger.py (line 154-155):
  workflow_name = RESOURCE_TYPE_WORKFLOW_MAP[ResourceType(rtype)]
  workflow_file = f"ferry-{workflow_name}.yml"
  # Result: "ferry-lambdas.yml", "ferry-step_functions.yml", "ferry-api_gateways.yml"
```

### Target Architecture (After)

```
constants.py:
  WORKFLOW_FILENAME = "ferry.yml"
  # RESOURCE_TYPE_WORKFLOW_MAP is deleted
  # ResourceType enum is kept (used by __init__.py export, may be used elsewhere)

trigger.py (line 154):
  workflow_file = WORKFLOW_FILENAME
  # All types dispatch to the same file
```

### Source File: constants.py

**Path:** `utils/src/ferry_utils/constants.py`
**Current state:** 23 lines. Defines `SCHEMA_VERSION`, `ResourceType` enum, `RESOURCE_TYPE_WORKFLOW_MAP` dict.

**Changes:**
1. Remove `RESOURCE_TYPE_WORKFLOW_MAP` (lines 17-22)
2. Add `WORKFLOW_FILENAME = "ferry.yml"` constant

**Keep:** `ResourceType` enum stays. It is exported via `ferry_utils/__init__.py` (`from ferry_utils.constants import SCHEMA_VERSION, ResourceType`) and may be used by downstream code.

**After:**
```python
"""Ferry shared constants and enums."""

from enum import StrEnum

# Dispatch payload schema version
SCHEMA_VERSION = 1


class ResourceType(StrEnum):
    """Supported serverless resource types."""

    LAMBDA = "lambda"
    STEP_FUNCTION = "step_function"
    API_GATEWAY = "api_gateway"


# Unified workflow filename for all dispatch types
WORKFLOW_FILENAME = "ferry.yml"
```

### Source File: trigger.py

**Path:** `backend/src/ferry_backend/dispatch/trigger.py`
**Current state:** 186 lines. Imports `RESOURCE_TYPE_WORKFLOW_MAP` and `ResourceType` from constants.

**Changes:**
1. Change import: `from ferry_utils.constants import RESOURCE_TYPE_WORKFLOW_MAP, ResourceType` becomes `from ferry_utils.constants import WORKFLOW_FILENAME`
2. Replace lines 153-155:
   ```python
   # BEFORE (lines 153-155):
   workflow_name = RESOURCE_TYPE_WORKFLOW_MAP[ResourceType(rtype)]
   workflow_file = f"ferry-{workflow_name}.yml"

   # AFTER (single line):
   workflow_file = WORKFLOW_FILENAME
   ```

**Note:** `ResourceType` import is removed because it was only used for the map lookup. It is not used anywhere else in trigger.py.

### Source File: parse_payload.py

**Path:** `action/src/ferry_action/parse_payload.py`
**Current state:** 137 lines. The `main()` function (lines 118-136) reads payload, builds matrix, sets output.

**Changes:**
1. In `main()`, after `set_output("matrix", matrix_json)` (line 132), add:
   ```python
   # Extract resource_type for job routing
   payload = DispatchPayload.model_validate_json(payload_str)
   set_output("resource_type", payload.resource_type)
   ```

**Optimization:** The `build_matrix()` function already parses the payload internally but doesn't return it. Rather than parsing twice, refactor `main()` to parse once and reuse. Two approaches:

**Approach A (minimal, parse twice):**
```python
def main() -> None:
    payload_str = os.environ.get("INPUT_PAYLOAD")
    if not payload_str:
        error("INPUT_PAYLOAD environment variable is not set or empty")
        sys.exit(1)

    try:
        matrix = build_matrix(payload_str)
    except Exception as exc:
        error(f"Failed to parse dispatch payload: {exc}")
        sys.exit(1)

    matrix_json = json.dumps(matrix, separators=(",", ":"))
    set_output("matrix", matrix_json)

    # Parse again to get resource_type for job routing
    payload = DispatchPayload.model_validate_json(payload_str)
    set_output("resource_type", payload.resource_type)
```

**Approach B (cleaner, parse once):**
```python
def main() -> None:
    payload_str = os.environ.get("INPUT_PAYLOAD")
    if not payload_str:
        error("INPUT_PAYLOAD environment variable is not set or empty")
        sys.exit(1)

    try:
        payload = DispatchPayload.model_validate_json(payload_str)
    except Exception as exc:
        error(f"Failed to parse dispatch payload: {exc}")
        sys.exit(1)

    builder = _MATRIX_BUILDERS.get(payload.resource_type)
    matrix = {"include": builder(payload)} if builder else {"include": []}

    matrix_json = json.dumps(matrix, separators=(",", ":"))
    set_output("matrix", matrix_json)
    set_output("resource_type", payload.resource_type)
```

**Recommendation:** Use Approach A. It is simpler (1 additional line + 1 import), does not change the internal structure of `build_matrix()`, and the double parse is negligible for a JSON payload under 65KB. Keep `build_matrix()` as a pure function -- it is tested independently by 17 tests.

### Source File: setup/action.yml

**Path:** `action/setup/action.yml`
**Current state:** 34 lines. Has one output (`matrix`).

**Changes:** Add `resource_type` output.

**After:**
```yaml
name: "Ferry Setup"
description: "Parse Ferry dispatch payload and output matrix for fan-out"

inputs:
  payload:
    description: "Raw dispatch payload JSON string"
    required: true

outputs:
  matrix:
    description: "JSON string for fromJson() in GHA strategy matrix"
    value: ${{ steps.parse.outputs.matrix }}
  resource_type:
    description: "Resource type string for conditional job routing"
    value: ${{ steps.parse.outputs.resource_type }}

runs:
  using: composite
  steps:
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.14"

    - name: Install uv
      uses: astral-sh/setup-uv@v4

    - name: Install ferry-action package
      shell: bash
      run: uv pip install --quiet --system "${{ github.action_path }}/.."

    - name: Parse dispatch payload
      id: parse
      shell: bash
      env:
        INPUT_PAYLOAD: ${{ inputs.payload }}
      run: python -m ferry_action.parse_payload
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parsing dispatch payload twice | Custom extraction of resource_type from JSON | `DispatchPayload.model_validate_json()` | Pydantic validates the full schema; raw JSON parsing would skip validation |
| GHA output writing | Manual file append | Existing `set_output()` in `gha.py` | Handles both `GITHUB_OUTPUT` file and fallback for local testing |

## Common Pitfalls

### Pitfall 1: Test URL Mocks Must Change Atomically
**What goes wrong:** If `constants.py` is changed to `WORKFLOW_FILENAME = "ferry.yml"` but test mocks still register responses for `ferry-lambdas.yml`, all dispatch tests fail with `httpx.TimeoutException` (no matching mock).
**Why it happens:** pytest-httpx is strict -- unmatched URLs cause test failures.
**How to avoid:** Change source code AND all test assertions/mocks in the same commit.
**Exact locations to update:**

In `tests/test_backend/test_dispatch_trigger.py`:
- Line 76: URL mock `ferry-lambdas.yml` -> `ferry.yml`
- Line 119: Assertion `results[0]["workflow"] == "ferry-lambdas.yml"` -> `"ferry.yml"`
- Line 134: URL mock `ferry-lambdas.yml` -> `ferry.yml`
- Line 141: URL mock `ferry-step_functions.yml` -> `ferry.yml`
- Line 210: URL mock `ferry-lambdas.yml` -> `ferry.yml`
- Line 265: URL mock `ferry-lambdas.yml` -> `ferry.yml`
- Line 306: Docstring mentions per-type filenames (update text)
- Line 310: URL mock `ferry-lambdas.yml` -> `ferry.yml`
- Line 317: URL mock `ferry-step_functions.yml` -> `ferry.yml`
- Line 363: Assertion `"ferry-lambdas.yml" in workflows` -> `"ferry.yml"`
- Line 364: Assertion `"ferry-step_functions.yml" in workflows` -> `"ferry.yml"`
- Line 371: URL mock `ferry-lambdas.yml` -> `ferry.yml`

In `tests/test_backend/test_handler_phase2.py`:
- Line 193: Default parameter `workflow_file="ferry-lambdas.yml"` -> `"ferry.yml"`

### Pitfall 2: test_trigger_dispatches_uses_correct_workflow_file Needs Redesign
**What goes wrong:** This test (line 305) currently verifies that different resource types dispatch to different workflow files. After the change, ALL types dispatch to `ferry.yml`, so the current assertion logic becomes meaningless.
**How to avoid:** Rewrite the test to verify that both lambda and step_function dispatches go to `ferry.yml`. The test should still verify 2 dispatches are made, but both use the same workflow filename.
**Updated assertion:**
```python
workflows = {r["workflow"] for r in results}
assert workflows == {"ferry.yml"}  # All types use same workflow
```

Also, since both dispatches now target the same URL (`ferry.yml/dispatches`), the httpx mock only needs ONE response registration (not two), but it needs to handle TWO requests. Use `httpx_mock.add_response()` once -- pytest-httpx allows multiple requests to match the same mock.

**Important:** Actually pytest-httpx by default consumes responses once. For two requests to the same URL, register the response twice:
```python
httpx_mock.add_response(url="...ferry.yml/dispatches", status_code=204)
httpx_mock.add_response(url="...ferry.yml/dispatches", status_code=204)
```

### Pitfall 3: test_trigger_dispatches_multiple_types Also Needs Two Mock Registrations
**What goes wrong:** The `test_trigger_dispatches_multiple_types` test (line 129) currently registers mocks for two different URLs. After the change, both dispatches go to the same URL. Need two registrations for the same URL.
**How to avoid:** Register `ferry.yml/dispatches` mock response twice.

### Pitfall 4: DispatchPayload Import in parse_payload.py
**What goes wrong:** Adding `set_output("resource_type", payload.resource_type)` requires `DispatchPayload` to be available in `main()`. Currently `DispatchPayload` is imported at the top of the file but only used inside `build_matrix()`.
**How to avoid:** The import already exists (line 16). Just use it directly in `main()`. No new import needed.

### Pitfall 5: test_valid_payload_writes_output Needs Updated Assertion
**What goes wrong:** The existing test at line 316 checks that GITHUB_OUTPUT contains `matrix=...`. After the change, the output file will also contain `resource_type=lambda`. The test should verify both outputs.
**How to avoid:** Update the assertion to check for both outputs:
```python
content = output_file.read_text()
lines = content.strip().split("\n")
assert len(lines) == 2
assert lines[0].startswith("matrix=")
assert lines[1] == "resource_type=lambda"
```

## Code Examples

### Complete constants.py After Change
```python
"""Ferry shared constants and enums."""

from enum import StrEnum

# Dispatch payload schema version
SCHEMA_VERSION = 1


class ResourceType(StrEnum):
    """Supported serverless resource types."""

    LAMBDA = "lambda"
    STEP_FUNCTION = "step_function"
    API_GATEWAY = "api_gateway"


# Unified workflow filename for all dispatch types
WORKFLOW_FILENAME = "ferry.yml"
```

### trigger.py Import and Dispatch Line Changes
```python
# BEFORE:
from ferry_utils.constants import RESOURCE_TYPE_WORKFLOW_MAP, ResourceType

# ... inside trigger_dispatches():
        workflow_name = RESOURCE_TYPE_WORKFLOW_MAP[ResourceType(rtype)]
        workflow_file = f"ferry-{workflow_name}.yml"

# AFTER:
from ferry_utils.constants import WORKFLOW_FILENAME

# ... inside trigger_dispatches():
        workflow_file = WORKFLOW_FILENAME
```

### parse_payload.py main() Addition
```python
# At end of main(), after set_output("matrix", matrix_json):
    payload = DispatchPayload.model_validate_json(payload_str)
    set_output("resource_type", payload.resource_type)
```

### Test Mock Update Pattern (test_dispatch_trigger.py)
```python
# BEFORE:
httpx_mock.add_response(
    url=(
        "https://api.github.com/repos/owner/repo"
        "/actions/workflows/ferry-lambdas.yml/dispatches"
    ),
    status_code=204,
)

# AFTER:
httpx_mock.add_response(
    url=(
        "https://api.github.com/repos/owner/repo"
        "/actions/workflows/ferry.yml/dispatches"
    ),
    status_code=204,
)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_backend/test_dispatch_trigger.py tests/test_action/test_parse_payload.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BE-01 | All dispatches target ferry.yml | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches -x` | Yes (update assertions) |
| BE-02 | RESOURCE_TYPE_WORKFLOW_MAP removed, WORKFLOW_FILENAME exists | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py -x` | Yes (update assertions) |
| ACT-01 | resource_type exposed as workflow output | unit | `uv run pytest tests/test_action/test_parse_payload.py::TestMain::test_valid_payload_writes_output -x` | Yes (update assertion) |
| ACT-02 | matrix output preserved | unit | `uv run pytest tests/test_action/test_parse_payload.py -x` | Yes (no change needed) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_backend/test_dispatch_trigger.py tests/test_action/test_parse_payload.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q` (note: handler_phase2 tests may fail due to AWS cred issue unrelated to this phase)
- **Phase gate:** `uv run pytest tests/test_backend/test_dispatch_trigger.py tests/test_action/test_parse_payload.py tests/test_utils/test_dispatch_models.py -x -q` (50 tests, currently passing)

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. No new test files needed, only assertion updates in existing tests.

## Complete Inventory of Changes

### Source Files (4 files)

| File | Path | Change Type | Lines Changed |
|------|------|-------------|---------------|
| constants.py | `utils/src/ferry_utils/constants.py` | Modify | Remove 6 lines (map), add 2 lines (constant) |
| trigger.py | `backend/src/ferry_backend/dispatch/trigger.py` | Modify | Change 1 import line, replace 2 lines with 1 |
| parse_payload.py | `action/src/ferry_action/parse_payload.py` | Modify | Add 2 lines after line 132 |
| action.yml | `action/setup/action.yml` | Modify | Add 3 lines (new output block) |

### Test Files (2 files)

| File | Path | Change Type | Tests Affected |
|------|------|-------------|---------------|
| test_dispatch_trigger.py | `tests/test_backend/test_dispatch_trigger.py` | Modify | 6 tests: URL mocks + assertions updated |
| test_handler_phase2.py | `tests/test_backend/test_handler_phase2.py` | Modify | 1 helper: default parameter updated |

### No-Touch Files (verification)
| File | Path | Reason |
|------|------|--------|
| test_parse_payload.py | `tests/test_action/test_parse_payload.py` | 1 test updated (`test_valid_payload_writes_output`) |
| test_dispatch_models.py | `tests/test_utils/test_dispatch_models.py` | No workflow filename references |
| dispatch.py (models) | `utils/src/ferry_utils/models/dispatch.py` | No change -- DispatchPayload schema unchanged |
| gha.py | `action/src/ferry_action/gha.py` | No change -- set_output already works |
| `__init__.py` | `utils/src/ferry_utils/__init__.py` | No change -- does not export RESOURCE_TYPE_WORKFLOW_MAP |

## Open Questions

None. All implementation details are fully specified. The changes are mechanical and well-bounded.

## Sources

### Primary (HIGH confidence)
- Direct code analysis of `utils/src/ferry_utils/constants.py` (23 lines)
- Direct code analysis of `backend/src/ferry_backend/dispatch/trigger.py` (186 lines)
- Direct code analysis of `action/src/ferry_action/parse_payload.py` (137 lines)
- Direct code analysis of `action/setup/action.yml` (34 lines)
- Direct code analysis of `action/src/ferry_action/gha.py` (106 lines)
- Direct code analysis of `utils/src/ferry_utils/models/dispatch.py` (74 lines)
- Direct code analysis of `tests/test_backend/test_dispatch_trigger.py` (507 lines)
- Direct code analysis of `tests/test_action/test_parse_payload.py` (338 lines)
- Direct code analysis of `tests/test_backend/test_handler_phase2.py` (734 lines)
- Direct code analysis of `tests/test_utils/test_dispatch_models.py` (294 lines)
- Test suite verification: 50 tests passing (`test_dispatch_trigger` + `test_parse_payload` + `test_dispatch_models`)
- Project research: `.planning/research/SUMMARY.md`, `.planning/research/ARCHITECTURE.md`

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct code analysis

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, pure refactor of existing code
- Architecture: HIGH - all source files read line-by-line, every change location identified
- Pitfalls: HIGH - all test assertions identified by line number, mock patterns verified against pytest-httpx behavior
- Test impact: HIGH - test suite run confirmed 50 tests passing, all affected assertions catalogued

**Research date:** 2026-03-10
**Valid until:** No expiry -- findings are based on current codebase state, not external dependencies
