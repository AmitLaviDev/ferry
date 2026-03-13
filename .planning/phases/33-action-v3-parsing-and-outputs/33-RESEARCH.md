# Phase 33: Action v3 Parsing and Outputs - Research

**Researched:** 2026-03-13
**Domain:** GitHub Actions composite action output wiring, Pydantic model extension, Python dataclass extension
**Confidence:** HIGH

## Summary

This phase adds `mode` and `environment` as new outputs from the Ferry setup action. The changes are entirely mechanical: add two fields to the v1 `DispatchPayload` model, add two fields to the `ParseResult` dataclass, extract them in both `_parse_v1()` and `_parse_v2()`, output them in `main()`, and declare them in `action/setup/action.yml`. The v2 `BatchedDispatchPayload` already has these fields (added in phase 29), so the v2 path just needs to forward them.

The main subtlety is the v1 `DispatchPayload` model change. Currently this model does NOT have `mode` or `environment` fields. Adding them with defaults (`mode="deploy"`, `environment=""`) is safe because: (a) Pydantic models with defaults accept payloads that omit those fields, and (b) the v1 format is only used for the >65KB fallback path, which is an edge case. However, an existing test (`test_v1_payload_still_unchanged`) explicitly asserts `not hasattr(payload, "mode")` -- this test MUST be updated since the whole point of this phase is to add these fields.

**Primary recommendation:** This is a straightforward 4-file change with no external dependencies. The implementation can follow the existing patterns exactly -- add fields, forward them through the parse pipeline, output them via `set_output()`, and declare them in the action YAML.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **Outputs: mode and environment only (no head_ref/base_ref)** -- The setup action adds two new GHA outputs: `mode` and `environment`. The `head_ref` and `base_ref` fields from the payload are NOT exposed as outputs.
2. **Add mode and environment to v1 DispatchPayload** -- Add `mode: str = "deploy"` and `environment: str = ""` to the v1 `DispatchPayload` model for the >65KB fallback path.
3. **v1 parser extracts mode/environment from payload** -- `_parse_v1()` reads `mode` and `environment` from the parsed `DispatchPayload` model (not hardcoded defaults).

### Claude's Discretion
None specified -- all decisions are locked.

### Deferred Ideas (OUT OF SCOPE)
- Per-resource status in apply comment
- head_ref/base_ref as GHA outputs
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMPAT-02 | Setup action outputs `mode` and `environment` for workflow consumption | All findings below directly enable this -- model extension, ParseResult extension, main() output wiring, action.yml declaration |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic | v2 | Data model for dispatch payloads | Already used throughout project |
| Python dataclasses | stdlib | ParseResult dataclass | Already used for ParseResult |

### Supporting
No additional libraries needed. This phase uses only existing project infrastructure.

## Architecture Patterns

### Pattern 1: Pydantic Model Field Extension with Defaults
**What:** Add optional fields with defaults to a frozen Pydantic model.
**When to use:** When extending a payload schema while maintaining backward compatibility.
**Example:**
```python
# Source: existing BatchedDispatchPayload pattern in dispatch.py
class DispatchPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ... existing fields ...
    mode: str = "deploy"       # NEW - defaults safely for old payloads
    environment: str = ""      # NEW - defaults safely for old payloads
```

### Pattern 2: Frozen Dataclass Field Extension
**What:** Add fields to a frozen dataclass.
**When to use:** When extending ParseResult with new parsed values.
**Example:**
```python
# Source: existing ParseResult in parse_payload.py
@dataclass(frozen=True)
class ParseResult:
    lambda_matrix: dict
    sf_matrix: dict
    ag_matrix: dict
    has_lambdas: bool
    has_step_functions: bool
    has_api_gateways: bool
    resource_types: str
    mode: str           # NEW
    environment: str    # NEW
```

### Pattern 3: set_output() for GHA Outputs
**What:** Write key=value pairs to GITHUB_OUTPUT file.
**When to use:** Every output from main() in parse_payload.py.
**Example:**
```python
# Source: existing main() in parse_payload.py
set_output("mode", result.mode)
set_output("environment", result.environment)
```

### Pattern 4: action.yml Output Declaration
**What:** Declare outputs in composite action YAML, referencing step outputs.
**When to use:** Adding new outputs to the setup action.
**Example:**
```yaml
# Source: existing action/setup/action.yml
outputs:
  mode:
    description: "Dispatch mode ('deploy')"
    value: ${{ steps.parse.outputs.mode }}
  environment:
    description: "Target environment name (empty string if no environment)"
    value: ${{ steps.parse.outputs.environment }}
```

### Anti-Patterns to Avoid
- **Hardcoding defaults in the parser instead of reading from the model:** The CONTEXT.md explicitly says `_parse_v1()` should read from `payload.mode` and `payload.environment`, not return hardcoded `"deploy"` and `""`. This matters because the >65KB fallback path will carry real values.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| N/A | N/A | N/A | This phase is pure field-addition, no complex logic |

## Common Pitfalls

### Pitfall 1: Forgetting to Update the Existing Guard-Rail Test
**What goes wrong:** The test `test_v1_payload_still_unchanged` at line 647-672 of `test_dispatch_models.py` asserts `not hasattr(payload, "mode")` and `not hasattr(payload, "environment")`. After adding these fields to `DispatchPayload`, this test WILL FAIL.
**Why it happens:** The test was written as a guard rail in phase 29 to ensure v1 was NOT changed when v2 was extended. Now the intent has changed.
**How to avoid:** Update this test to assert `payload.mode == "deploy"` and `payload.environment == ""` instead. Also remove the `not hasattr` assertions for `head_ref` and `base_ref` if desired, but per CONTEXT.md, only `mode` and `environment` are being added -- `head_ref`/`base_ref` are NOT being added to v1, so those `not hasattr` assertions should REMAIN.
**Warning signs:** `test_v1_payload_still_unchanged` fails immediately after model change.

### Pitfall 2: Forgetting to Update action.yml
**What goes wrong:** Python code outputs `mode` and `environment` to GITHUB_OUTPUT, but the composite action YAML doesn't declare them as outputs. Downstream workflow jobs can't access them.
**Why it happens:** Easy to focus on Python code and forget the YAML plumbing.
**How to avoid:** `action/setup/action.yml` must add `mode` and `environment` under `outputs:` referencing `${{ steps.parse.outputs.mode }}` and `${{ steps.parse.outputs.environment }}`.
**Warning signs:** Workflow template references `steps.setup.outputs.mode` and gets empty string.

### Pitfall 3: Forgetting to Update Line Count Assertion in test_main
**What goes wrong:** `test_valid_payload_writes_output` (line 516) and `test_valid_v2_payload_writes_output` (line 554) both assert `len(lines) == 7` -- the exact number of output lines written to GITHUB_OUTPUT. Adding 2 new outputs changes this to 9.
**Why it happens:** Brittle test that counts output lines.
**How to avoid:** Update both `assert len(lines) == 7` to `assert len(lines) == 9`. Also add assertions for the new `mode` and `environment` output values.
**Warning signs:** `TestMain` tests fail with "AssertionError: assert 9 == 7".

### Pitfall 4: ParseResult Constructor Calls Missing New Fields
**What goes wrong:** `_parse_v1()` and `_parse_v2()` both construct `ParseResult(...)`. After adding `mode` and `environment` as required fields (no defaults on the dataclass), forgetting to pass them causes TypeError.
**Why it happens:** Frozen dataclass fields without defaults are positional-required.
**How to avoid:** Add `mode=payload.mode` and `environment=payload.environment` to both `ParseResult(...)` constructor calls.
**Warning signs:** TypeError at runtime: "missing required positional argument".

### Pitfall 5: Backend Fallback Does Not Forward mode/environment
**What goes wrong:** `_dispatch_per_type()` in `trigger.py` (line 143) constructs `DispatchPayload(...)` without passing `mode` or `environment`. After adding these fields to the model, the defaults will apply (mode="deploy", environment=""), which is correct for current usage but will be wrong when a `/ferry apply` dispatch exceeds 65KB.
**Why it happens:** The fallback function signature doesn't accept mode/environment.
**How to avoid:** This is OUT OF SCOPE for phase 33 (action-side only). However, it should be noted as a future fix needed in the backend. Currently, the backend always dispatches `mode="deploy"` and environments are not yet production-critical, so the defaults are safe.
**Warning signs:** None currently -- becomes a problem only when `/ferry apply` with environment is implemented AND a payload exceeds 65KB.

## Code Examples

### Current State: Files to Modify

#### 1. `utils/src/ferry_utils/models/dispatch.py` -- DispatchPayload (lines 59-74)
Currently has: `v`, `resource_type`, `resources`, `trigger_sha`, `deployment_tag`, `pr_number`.
Needs: `mode: str = "deploy"` and `environment: str = ""` added after `pr_number`.

#### 2. `action/src/ferry_action/parse_payload.py` -- ParseResult (lines 27-36)
Currently has 7 fields. Needs `mode: str` and `environment: str` added at end.

#### 3. `action/src/ferry_action/parse_payload.py` -- _parse_v1() (lines 144-165)
Currently returns `ParseResult(...)` without mode/environment. Needs `mode=payload.mode, environment=payload.environment`.

#### 4. `action/src/ferry_action/parse_payload.py` -- _parse_v2() (lines 168-224)
Currently returns `ParseResult(...)` without mode/environment. Needs `mode=payload.mode, environment=payload.environment`.

#### 5. `action/src/ferry_action/parse_payload.py` -- main() (lines 227-250)
Currently outputs 7 values. Needs two more `set_output()` calls for mode and environment.

#### 6. `action/setup/action.yml` -- outputs section (lines 9-30)
Currently declares 7 outputs. Needs `mode` and `environment` added.

### Tests That Need Updating

| Test File | Test Name | Current Assertion | Required Change |
|-----------|-----------|-------------------|-----------------|
| `test_dispatch_models.py` | `test_v1_payload_still_unchanged` (line 647) | `not hasattr(payload, "mode")` | Change to `payload.mode == "deploy"` |
| `test_dispatch_models.py` | `test_v1_payload_still_unchanged` (line 647) | `not hasattr(payload, "environment")` | Change to `payload.environment == ""` |
| `test_dispatch_models.py` | `test_v1_payload_still_unchanged` (line 647) | `not hasattr(payload, "head_ref")` | KEEP -- head_ref NOT added to v1 |
| `test_dispatch_models.py` | `test_v1_payload_still_unchanged` (line 647) | `not hasattr(payload, "base_ref")` | KEEP -- base_ref NOT added to v1 |
| `test_parse_payload.py` | `test_valid_payload_writes_output` (line 516) | `len(lines) == 7` | Change to `len(lines) == 9` |
| `test_parse_payload.py` | `test_valid_v2_payload_writes_output` (line 554) | `len(lines) == 7` | Change to `len(lines) == 9` |

### New Tests Needed

1. **test_v1_payload_mode_defaults** -- DispatchPayload without mode/environment gets defaults
2. **test_v1_payload_mode_explicit** -- DispatchPayload with explicit mode/environment values
3. **test_v1_parse_mode_defaults** -- parse_payload with v1 payload returns mode="deploy", environment=""
4. **test_v1_parse_mode_explicit** -- parse_payload with v1 payload containing mode/environment returns those values
5. **test_v2_parse_mode_defaults** -- parse_payload with v2 payload (no mode/env) returns defaults
6. **test_v2_parse_mode_explicit** -- parse_payload with v2 payload containing mode="deploy", environment="staging"
7. **test_main_v1_outputs_mode_environment** -- main() with v1 payload writes mode and environment to GITHUB_OUTPUT
8. **test_main_v2_outputs_mode_environment** -- main() with v2 payload writes mode and environment to GITHUB_OUTPUT

### Test Helper Updates

The `_make_payload()` helper needs `mode` and `environment` optional parameters:
```python
def _make_payload(
    *,
    resources: list[dict] | None = None,
    trigger_sha: str = "abc1234def5678",
    deployment_tag: str = "pr-42",
    resource_type: str = "lambda",
    mode: str | None = None,         # NEW
    environment: str | None = None,   # NEW
) -> str:
```

The `_make_batched_payload()` helper needs `mode` and `environment` optional parameters:
```python
def _make_batched_payload(
    *,
    lambdas: list[dict] | None = None,
    step_functions: list[dict] | None = None,
    api_gateways: list[dict] | None = None,
    trigger_sha: str = "abc1234def5678",
    deployment_tag: str = "pr-42",
    mode: str | None = None,         # NEW
    environment: str | None = None,   # NEW
) -> str:
```

## State of the Art

No ecosystem changes relevant -- this is internal field plumbing.

## Open Questions

1. **Backend fallback forwarding mode/environment**
   - What we know: `_dispatch_per_type()` in `trigger.py` does not pass mode/environment when constructing v1 payloads for the >65KB fallback.
   - What's unclear: Whether this should be fixed in this phase or deferred.
   - Recommendation: Defer to a future phase. The fallback defaults (mode="deploy", environment="") are correct for all current usage. This only matters when `/ferry apply` with environment is implemented AND a payload exceeds 65KB -- an extremely unlikely edge case.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` (project-level) |
| Quick run command | `.venv/bin/python -m pytest tests/test_action/test_parse_payload.py tests/test_utils/test_dispatch_models.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMPAT-02 | v1 DispatchPayload has mode/environment defaults | unit | `.venv/bin/python -m pytest tests/test_utils/test_dispatch_models.py -x -q` | Exists (needs update) |
| COMPAT-02 | ParseResult includes mode/environment from v1 payload | unit | `.venv/bin/python -m pytest tests/test_action/test_parse_payload.py -x -q` | Exists (needs new tests) |
| COMPAT-02 | ParseResult includes mode/environment from v2 payload | unit | `.venv/bin/python -m pytest tests/test_action/test_parse_payload.py -x -q` | Exists (needs new tests) |
| COMPAT-02 | main() writes mode/environment to GITHUB_OUTPUT | unit | `.venv/bin/python -m pytest tests/test_action/test_parse_payload.py::TestMain -x -q` | Exists (needs update + new tests) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_action/test_parse_payload.py tests/test_utils/test_dispatch_models.py -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before verification

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. Only test content updates needed, no framework or fixture gaps.

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all 4 target files in the repository
- Direct code inspection of `trigger.py` for understanding upstream consumers
- Direct code inspection of `action/setup/action.yml` for output declaration pattern
- Running existing test suite: 68 tests pass (0 failures)

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions from user discussion

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, purely extending existing patterns
- Architecture: HIGH - exact patterns visible in existing code
- Pitfalls: HIGH - identified all 5 pitfalls through direct code analysis

**Research date:** 2026-03-13
**Valid until:** No expiration -- this is purely internal code analysis, not dependent on external libraries
