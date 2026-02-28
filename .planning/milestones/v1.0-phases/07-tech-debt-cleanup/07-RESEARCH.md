# Phase 7: Tech Debt Cleanup - Research

**Researched:** 2026-02-27
**Domain:** Codebase consistency, runtime pipeline wiring, documentation, planning metadata
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Workflow documentation**: Standalone `docs/` directory, not embedded in README. One document per resource type (lambdas, step_functions, api_gateways) plus a shared page for common concepts. Full setup guide with annotated copy-paste example workflow files (inline YAML comments explaining each field). Cover the naming convention (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) and why it matters.
- **Runtime default resolution**: Canonical default `python3.14`. Wire runtime end-to-end: ferry.yaml `LambdaConfig.runtime` flows through dispatch payload to build action. Default lives in `LambdaConfig` schema only (single source of truth) -- `parse_payload.py` receives it from dispatch, no hardcoded fallback. Documentation should explain the default is overridable at the workflow level.
- **SUMMARY frontmatter**: Backfill `requirements-completed` field in ALL existing SUMMARY.md files. Cross-validate against VERIFICATION.md and REQUIREMENTS.md -- fix any mismatches found. Format for plans with no requirements: Claude's discretion (empty array or omit).
- **Scope of cleanup**: Core 3 audit items + runtime end-to-end wiring. Quick sweep of entire codebase (production code, tests, docs) for trivial inconsistencies. Fix trivial issues silently (one-liner fixes: stale comments, wrong defaults, mismatched types). Flag non-trivial issues that need design decisions.

### Claude's Discretion
- How to handle SUMMARY files for plans that don't map to specific requirements (empty array vs omit)
- Organization of shared vs per-type documentation pages
- What counts as "trivial" vs "non-trivial" during the sweep
- Exact runtime wiring approach through dispatch models

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Summary

Phase 7 is a well-scoped cleanup of three tech debt items identified by the milestone audit, plus end-to-end runtime wiring through the dispatch pipeline. The work spans four areas: (1) resolving the runtime default inconsistency where `LambdaConfig.runtime` defaults to `python3.10` while `parse_payload.py` hardcodes `python3.12` and the composite action defaults to `python3.12` -- all must become `python3.14` with runtime flowing through the dispatch payload; (2) creating user-facing workflow documentation in a new `docs/` directory; (3) verifying (and if needed backfilling) `requirements-completed` frontmatter in SUMMARY.md files; and (4) a codebase-wide sweep for trivial inconsistencies like stale docstrings.

The runtime wiring is the most technically involved item. It follows the exact same pattern as Phase 6's `function_name` wiring: add a `runtime` field to `LambdaResource` in the dispatch model, populate it from `LambdaConfig.runtime` in `_build_resource`, read it in `parse_payload.py` instead of hardcoding, and pass it through the GHA matrix to the build action. The pattern is proven -- Phase 6 completed it in 4 minutes for `function_name`. The documentation work is greenfield (no `docs/` directory exists yet) but the content is well-defined by the existing `RESOURCE_TYPE_WORKFLOW_MAP` constants and composite action YAML files.

**Primary recommendation:** Follow the Phase 6 `function_name` wiring pattern for `runtime`, change the canonical default to `python3.14`, create `docs/` with one file per resource type plus a shared concepts page, and verify SUMMARY frontmatter cross-references.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic v2 | 2.x | Dispatch model field addition (`runtime` on `LambdaResource`) | Already the project's data contract layer |
| PyYAML | stable | No new dependency -- already used | ferry.yaml parsing exists |

### Supporting
No new libraries needed. This phase modifies existing code and creates documentation files.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Adding `runtime` to dispatch model | Keep runtime as build-only concern with hardcoded default | Violates "single source of truth" -- user's ferry.yaml runtime would be ignored by the action |

## Architecture Patterns

### Pattern 1: End-to-End Field Wiring (proven in Phase 6)

**What:** Add a field to `LambdaResource` dispatch model, populate from `LambdaConfig`, surface in `parse_payload.py` matrix output, consume in composite action.

**When to use:** Whenever a ferry.yaml config field needs to flow from the backend through dispatch to the action.

**The pipeline (4 touch points):**
```
LambdaConfig.runtime (schema.py, single default)
  -> LambdaResource.runtime (dispatch.py, required str)
    -> _build_resource passes runtime= (trigger.py)
      -> _build_lambda_matrix includes "runtime" from r.runtime (parse_payload.py)
        -> GHA matrix -> action.yml INPUT_RUNTIME -> build.py reads it
```

**Phase 6 precedent:** `function_name` was wired through this exact pipeline in plan 06-01. The pattern was: add field to model, update `_build_resource` constructor, update matrix builder, update all test construction sites.

### Pattern 2: Hardcoded-to-Wired Migration

**What:** Replace a hardcoded value in the middle of a pipeline with a value that flows from the source of truth.

**Current state for runtime:**
```
LambdaConfig.runtime = "python3.10"  (backend default)
parse_payload.py "runtime": "python3.12"  (hardcoded in action, different value!)
action.yml runtime default: "python3.12"  (composite action input default)
Dockerfile ARG PYTHON_VERSION=3.12  (Dockerfile default)
```

**Target state:**
```
LambdaConfig.runtime = "python3.14"  (single source of truth)
LambdaResource.runtime: str  (dispatch model carries it)
_build_resource: runtime=lam.runtime  (trigger passes it)
_build_lambda_matrix: "runtime": r.runtime  (from dispatch, no hardcoded fallback)
action.yml runtime default: "python3.14"  (fallback if not from matrix)
Dockerfile ARG PYTHON_VERSION=3.14  (Dockerfile default matches)
```

### Anti-Patterns to Avoid
- **Multiple defaults for the same concept:** The current state has `python3.10` in schema.py, `python3.12` in parse_payload.py, and `python3.12` in action.yml. After this phase, `python3.14` lives in `LambdaConfig` only; everything else receives it from the pipeline.
- **Hardcoded fallbacks masking pipeline bugs:** If `parse_payload.py` hardcodes a runtime value, a broken pipeline is invisible -- the action always gets *something*. Removing the hardcoded value means a missing runtime in the dispatch payload will surface as a clear error.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown documentation | Custom doc generator | Plain markdown files in `docs/` | Documentation is 4 files; no tooling needed |
| SUMMARY frontmatter validation | Custom YAML frontmatter parser | Manual inspection + grep | Only 13 files to check; already verified all have the field |

**Key insight:** This phase is intentionally low-tech. The value comes from consistency, not new infrastructure.

## Common Pitfalls

### Pitfall 1: Test Cascade from Runtime Default Change
**What goes wrong:** Changing `LambdaConfig.runtime` default from `python3.10` to `python3.14` breaks every test that asserts the old default.
**Why it happens:** Tests hardcode expected default values.
**How to avoid:** Search for ALL occurrences of `python3.10` and `python3.12` in test files. Update assertions systematically.
**Warning signs:** Tests pass individually but fail in aggregate because some were updated and others weren't.

**Files that will need test updates (verified by grep):**
- `tests/test_backend/test_config_schema.py` (line 29, 32: asserts `python3.10` default)
- `tests/test_backend/test_changes.py` (lines 297, 307, 364, 382: uses `python3.10` and `python3.12` for change detection tests -- these test that different runtimes produce a "modified" change; the specific values don't need to change unless they relied on the default)
- `tests/test_action/test_parse_payload.py` (line 66: asserts `python3.12` runtime in matrix)
- `tests/test_action/test_build.py` (lines 177, 246: uses `python3.12` as test input -- these are explicit overrides, not defaults, so they're fine)

### Pitfall 2: Dispatch Model Backward Compatibility
**What goes wrong:** Adding `runtime` as a required field on `LambdaResource` means old payloads without `runtime` will fail validation.
**Why it happens:** The dispatch model is a contract between backend and action; both must be deployed in sync.
**How to avoid:** Since Ferry is pre-release (v1 not shipped), backward compatibility is not a concern. In production, this would require a schema version bump and migration period.
**Warning signs:** N/A for pre-release.

### Pitfall 3: Docstring Staleness After Wiring
**What goes wrong:** The `build_matrix` docstring (parse_payload.py lines 101-105) already omits `function_name` from its field list. After adding runtime-from-dispatch, the docstring must be updated to reflect that runtime is no longer hardcoded.
**Why it happens:** Docstrings don't trigger test failures.
**How to avoid:** Include docstring updates in the same task as the code change. The Phase 6 verification already flagged the `function_name` omission.

### Pitfall 4: Dockerfile Default Drift
**What goes wrong:** The Dockerfile `ARG PYTHON_VERSION=3.12` is a fallback for manual builds. If it doesn't match the canonical default, someone building the Dockerfile directly gets a different runtime than ferry.yaml specifies.
**How to avoid:** Update the Dockerfile ARG default to `3.14` alongside the LambdaConfig default.

## Code Examples

### Runtime Field Addition to LambdaResource (dispatch.py)
```python
# Before (current):
class LambdaResource(BaseModel):
    model_config = ConfigDict(frozen=True)
    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str
    function_name: str

# After:
class LambdaResource(BaseModel):
    model_config = ConfigDict(frozen=True)
    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str
    function_name: str
    runtime: str
```

### Runtime Wiring in _build_resource (trigger.py)
```python
# Before (current):
return LambdaResource(
    name=name,
    source=lam.source_dir,
    ecr=lam.ecr_repo,
    function_name=lam.function_name,
)

# After:
return LambdaResource(
    name=name,
    source=lam.source_dir,
    ecr=lam.ecr_repo,
    function_name=lam.function_name,
    runtime=lam.runtime,
)
```

### Runtime From Dispatch in parse_payload.py (remove hardcoded default)
```python
# Before (current):
def _build_lambda_matrix(payload: DispatchPayload) -> list[dict]:
    return [
        {
            "name": r.name,
            "source": r.source,
            "ecr": r.ecr,
            "function_name": r.function_name,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
            "runtime": "python3.12",  # HARDCODED -- tech debt
        }
        for r in payload.resources
        if isinstance(r, LambdaResource)
    ]

# After:
def _build_lambda_matrix(payload: DispatchPayload) -> list[dict]:
    return [
        {
            "name": r.name,
            "source": r.source,
            "ecr": r.ecr,
            "function_name": r.function_name,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
            "runtime": r.runtime,  # From dispatch payload (source of truth: LambdaConfig)
        }
        for r in payload.resources
        if isinstance(r, LambdaResource)
    ]
```

### Workflow Documentation Structure (docs/)
```
docs/
├── setup.md              # Shared concepts: installation, ferry.yaml structure, OIDC setup
├── lambdas.md            # Lambda workflow: ferry-lambdas.yml, build+deploy, runtime override
├── step-functions.md     # Step Functions workflow: ferry-step_functions.yml, definition files
└── api-gateways.md       # API Gateway workflow: ferry-api_gateways.yml, OpenAPI specs
```

Each file includes:
- What the workflow does
- Full annotated copy-paste YAML example with inline comments
- Naming convention explanation: `ferry-{RESOURCE_TYPE_WORKFLOW_MAP[type]}.yml`
- Required inputs and what each means
- How to customize (runtime override for lambdas, etc.)

## Detailed Inventory of Changes

### Item 1: Runtime Default Inconsistency + End-to-End Wiring

**Current state (3 different defaults):**
| Location | Value | Role |
|----------|-------|------|
| `backend/src/ferry_backend/config/schema.py:23` | `python3.10` | LambdaConfig default |
| `action/src/ferry_action/parse_payload.py:40` | `python3.12` | Hardcoded in matrix builder |
| `action/build/action.yml:30` | `python3.12` | Composite action input default |
| `action/Dockerfile:2` | `3.12` | Dockerfile ARG default |

**Target state (single source of truth: `python3.14`):**
| Location | New Value | Change Type |
|----------|-----------|-------------|
| `backend/src/ferry_backend/config/schema.py:23` | `python3.14` | Default change |
| `utils/src/ferry_utils/models/dispatch.py` | Add `runtime: str` to `LambdaResource` | New field |
| `backend/src/ferry_backend/dispatch/trigger.py` | Pass `runtime=lam.runtime` | Constructor arg |
| `action/src/ferry_action/parse_payload.py:40` | `"runtime": r.runtime` (from model, not hardcoded) | Remove hardcoded default |
| `action/src/ferry_action/parse_payload.py:26-29` | Update/remove stale docstring about runtime being build-only concern | Docstring fix |
| `action/src/ferry_action/parse_payload.py:101` | Add `function_name` to field list, update runtime note | Docstring fix |
| `action/build/action.yml:30` | `python3.14` | Fallback default |
| `action/Dockerfile:2` | `3.14` | Dockerfile ARG default |

**Test files requiring updates:**
| File | Lines | What Changes |
|------|-------|-------------|
| `tests/test_backend/test_config_schema.py` | 29, 32 | Assert `python3.14` instead of `python3.10` |
| `tests/test_action/test_parse_payload.py` | 66 | Assert `python3.14` instead of `python3.12` (or update to check dynamic value from payload) |
| `tests/test_utils/test_dispatch_models.py` | Multiple | Add `runtime` to all `LambdaResource` constructions |
| `tests/test_backend/test_dispatch_trigger.py` | Multiple | Assert `runtime` in built resources |
| `tests/test_backend/test_changes.py` | 297, 307, 364, 382 | These tests explicitly set runtime values for diffing -- likely fine as-is since they don't rely on the default |
| `tests/test_action/test_build.py` | 177, 246 | These use explicit `INPUT_RUNTIME` env var -- likely fine |

### Item 2: Workflow Documentation

**Current state:** No `docs/` directory exists. No user-facing documentation about workflow files.

**What needs creating:**
- `docs/setup.md` -- Installation, ferry.yaml structure, OIDC setup, shared concepts
- `docs/lambdas.md` -- Lambda-specific workflow guide with annotated `ferry-lambdas.yml` example
- `docs/step-functions.md` -- Step Functions workflow with `ferry-step_functions.yml` example
- `docs/api-gateways.md` -- API Gateway workflow with `ferry-api_gateways.yml` example

**Key content sources (existing code to reference):**
- Workflow naming: `RESOURCE_TYPE_WORKFLOW_MAP` in `utils/src/ferry_utils/constants.py` -- maps `lambda` -> `lambdas`, `step_function` -> `step_functions`, `api_gateway` -> `api_gateways`
- Naming convention: `trigger.py:156` builds `ferry-{workflow_name}.yml`
- Composite action inputs: `action/build/action.yml`, `action/deploy/action.yml`, `action/deploy-stepfunctions/action.yml`, `action/deploy-apigw/action.yml`
- Setup action: `action/setup/action.yml` -- parses dispatch payload to matrix

### Item 3: SUMMARY Frontmatter Verification

**Current state:** All 13 plan SUMMARY files already have `requirements-completed` in their YAML frontmatter.

**Cross-reference check needed:**
| SUMMARY File | Claims | VERIFICATION.md Says | REQUIREMENTS.md Says |
|-------------|--------|---------------------|---------------------|
| 01-01 | ACT-02 | ACT-02 SATISFIED | ACT-02 -> Phase 1 Complete |
| 01-02 | WHOOK-01, WHOOK-02 | Both SATISFIED | Both -> Phase 1 Complete |
| 01-03 | AUTH-01 | AUTH-01 SATISFIED | AUTH-01 -> Phase 1 Complete |
| 02-01 | CONF-01, CONF-02 | Both SATISFIED | Both -> Phase 2 Complete |
| 02-02 | DETECT-01 | DETECT-01 SATISFIED | DETECT-01 -> Phase 2 Complete |
| 02-03 | DETECT-02, ORCH-01, ORCH-02 | All SATISFIED | All -> Phase 2 Complete |
| 03-01 | ACT-01, AUTH-02 | Both SATISFIED | Both -> Phase 3 Complete |
| 03-02 | BUILD-01-05 | All SATISFIED (via 03-VERIFICATION) | All -> Phase 3 Complete |
| 03-03 | DEPLOY-01, DEPLOY-04, DEPLOY-05 | DEPLOY-01 partially (fn_name break), DEPLOY-04/05 SATISFIED | DEPLOY-01 -> Phase 6 (later fixed); DEPLOY-04/05 -> Phase 3 Complete |
| 04-01 | DEPLOY-02, DEPLOY-03 | Both SATISFIED | Both -> Phase 4 Complete |
| 04-02 | DEPLOY-02 | DEPLOY-02 SATISFIED | DEPLOY-02 -> Phase 4 Complete |
| 04-03 | DEPLOY-03 | DEPLOY-03 SATISFIED | DEPLOY-03 -> Phase 4 Complete |
| 06-01 | DEPLOY-01 | DEPLOY-01 SATISFIED | DEPLOY-01 -> Phase 6 Complete |

**Potential mismatch noted:** 03-03-SUMMARY claims `DEPLOY-01` but Phase 6 was created specifically to fix the `function_name` pipeline break for DEPLOY-01. The 03-03 claim is partially correct (deploy.py was written in Phase 3, but the pipeline was broken). The REQUIREMENTS.md traceability table shows DEPLOY-01 mapped to Phase 6 (not Phase 3). This needs a decision: should 03-03 keep or remove DEPLOY-01 from its `requirements-completed`? Since Phase 6 was specifically a fix for the DEPLOY-01 pipeline break, the most accurate representation is that 03-03 implemented the deploy module (DEPLOY-04, DEPLOY-05) and 06-01 closed the DEPLOY-01 gap.

**Note:** The `.planning/research/SUMMARY.md` is a project research summary, not a plan summary -- it does not need `requirements-completed` frontmatter.

### Item 4: Codebase Sweep (trivial inconsistencies)

**Already identified:**
1. `parse_payload.py` line 101: `build_matrix` docstring lists lambda fields as "name, source, ecr, trigger_sha, deployment_tag, runtime" -- missing `function_name` (flagged by Phase 6 verification)
2. `parse_payload.py` lines 26-29: Stale comment saying "dispatch payload intentionally does not include runtime" -- will be wrong after runtime wiring
3. Multiple `# type: ignore[union-attr]` annotations on boto3 client calls -- these are intentional (boto3 typing limitation), not debt
4. `# type: ignore[call-arg]` in tests -- these are intentional (testing Pydantic validation rejects bad args)
5. `# type: ignore[operator]` in test_build.py -- tmp_path typing, intentional

**Sweep scope (production code + tests + docs):**
- Production Python files: 18 files across 3 packages
- Test files: ~12 test files
- Action YAML files: 5
- Dockerfile: 1

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded runtime in parse_payload.py | Runtime flows through dispatch pipeline | This phase | parse_payload.py no longer makes assumptions about runtime |
| No user docs | `docs/` directory with per-type guides | This phase | Users can set up workflows from documentation |

## Open Questions

1. **Should 03-03-SUMMARY keep `DEPLOY-01` in requirements-completed?**
   - What we know: 03-03 created `deploy.py`, but the `function_name` pipeline was broken (fixed in Phase 6). REQUIREMENTS.md maps DEPLOY-01 to Phase 6.
   - What's unclear: Is "partial implementation" worthy of the claim? Phase 3 created the deploy module; Phase 6 fixed the data pipeline.
   - Recommendation: Remove `DEPLOY-01` from 03-03-SUMMARY and keep it only in 06-01-SUMMARY. This matches REQUIREMENTS.md traceability and is the cleanest representation.

2. **Should action.yml `runtime` input default remain or be removed?**
   - What we know: After runtime flows through the dispatch pipeline, the matrix provides the runtime value. The action.yml default is a fallback for direct usage outside Ferry.
   - What's unclear: Will anyone invoke the action directly outside the Ferry pipeline?
   - Recommendation: Keep the action.yml default as `python3.14` (matches canonical). It's a safety net, not the primary path.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of all files listed in the inventory (first-party, authoritative)
- Phase 6 execution record (06-01-SUMMARY.md) -- confirms the `function_name` wiring pattern works in 4 minutes
- Phase 6 VERIFICATION.md -- flagged the `build_matrix` docstring omission
- REQUIREMENTS.md traceability table -- authoritative source for requirement-to-phase mapping
- All 13 SUMMARY.md files inspected via grep for `requirements-completed` field presence

### Secondary (MEDIUM confidence)
- None needed -- this phase is purely internal codebase work

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all changes are to existing code
- Architecture: HIGH -- runtime wiring follows proven Phase 6 `function_name` pattern exactly
- Pitfalls: HIGH -- all affected files identified by grep; test cascade is the main risk and file list is complete

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable -- internal codebase cleanup, no external dependencies)
