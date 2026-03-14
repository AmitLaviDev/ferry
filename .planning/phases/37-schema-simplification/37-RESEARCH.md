# Phase 37: Schema Simplification - Research

**Researched:** 2026-03-14
**Domain:** Pydantic schema, dispatch models, deploy pipeline, backward compatibility
**Confidence:** HIGH

## Summary

Phase 37 eliminates redundant field duplication in ferry.yaml where `name` and `function_name`/`state_machine_name` are separate fields but almost always identical. The change makes `name` the single source of truth for the AWS resource name across Lambdas and Step Functions, while API Gateways remain unchanged (they use `rest_api_id` and `stage_name` which are AWS IDs, not names).

The change touches four distinct layers: (1) the ferry.yaml Pydantic schema in the backend, (2) the dispatch payload models in ferry-utils, (3) the parse_payload and deploy modules in ferry-action, and (4) the GHA composite action.yml files and workflow template. Backward compatibility is needed at the ferry.yaml parsing layer (accept old field names as aliases) but NOT at the dispatch payload layer (the backend controls what gets dispatched).

**Primary recommendation:** Use Pydantic `model_validator(mode="before")` to accept old field names as aliases in `LambdaConfig` and `StepFunctionConfig`, then remove the fields from the dispatch pipeline entirely. The workflow template change is a breaking change that requires users to update `ferry.yml`, but since there are no external users, this is acceptable.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCHEMA-01 | `name` in ferry.yaml IS the AWS resource name -- no separate `function_name` / `state_machine_name` fields | Full codebase analysis of all 4 layers (schema, dispatch, deploy, GHA) completed below |
</phase_requirements>

## Impact Analysis

### Complete Field Flow Map

The `function_name` and `state_machine_name` fields flow through 4 layers:

**Layer 1: ferry.yaml Schema (backend)**
- `LambdaConfig.function_name` -- optional field, defaults to `name` via model_validator
- `StepFunctionConfig.state_machine_name` -- required field, no default

**Layer 2: Dispatch Payload Models (ferry-utils)**
- `LambdaResource.function_name` -- required field
- `StepFunctionResource.state_machine_name` -- required field
- Built by `_build_resource()` in `dispatch/trigger.py`

**Layer 3: Parse Payload (ferry-action)**
- `parse_payload.py` copies `function_name` and `state_machine_name` into GHA matrix dicts
- Both v1 `_build_lambda_matrix()` and v2 `_parse_v2()` emit these fields

**Layer 4: GHA Composite Actions + Workflow Template**
- `action/deploy/action.yml` -- accepts `function-name` input, sets `INPUT_FUNCTION_NAME` env
- `action/deploy-stepfunctions/action.yml` -- accepts `state-machine-name` input, sets `INPUT_STATE_MACHINE_NAME` env
- `ferry.yml` template -- passes `matrix.function_name` and `matrix.state_machine_name`
- `deploy.py` main() reads `INPUT_FUNCTION_NAME` env
- `deploy_stepfunctions.py` main() reads `INPUT_STATE_MACHINE_NAME` env

### Files That Must Change

| File | Change | Impact |
|------|--------|--------|
| `backend/src/ferry_backend/config/schema.py` | Remove `function_name` from LambdaConfig, remove `state_machine_name` from StepFunctionConfig, add backward-compat validator | Schema layer |
| `utils/src/ferry_utils/models/dispatch.py` | Remove `function_name` from LambdaResource, remove `state_machine_name` from StepFunctionResource | Dispatch payload |
| `backend/src/ferry_backend/dispatch/trigger.py` | `_build_resource()` stops passing `function_name`/`state_machine_name` | Dispatch building |
| `action/src/ferry_action/parse_payload.py` | Replace `function_name`/`state_machine_name` with `name` in matrix dicts | Matrix output |
| `action/src/ferry_action/deploy.py` | Read `INPUT_RESOURCE_NAME` as the function name (remove `INPUT_FUNCTION_NAME`) | Lambda deploy |
| `action/src/ferry_action/deploy_stepfunctions.py` | Read `INPUT_RESOURCE_NAME` as the state machine name (remove `INPUT_STATE_MACHINE_NAME`) | SF deploy |
| `action/deploy/action.yml` | Remove `function-name` input, stop setting `INPUT_FUNCTION_NAME` | GHA action |
| `action/deploy-stepfunctions/action.yml` | Remove `state-machine-name` input, stop setting `INPUT_STATE_MACHINE_NAME` | GHA action |
| `docs/setup.md` | Remove `function_name` and `state_machine_name` from examples, update workflow template | Docs |
| ferry-test-app `ferry.yaml` | Remove `function_name` field, change `name` to `ferry-test-hello-world`; change SF `name` to `ferry-test-sf` | Test repo |

### Test Files That Must Update

| Test File | What Changes |
|-----------|--------------|
| `tests/test_backend/test_config_schema.py` | Remove `function_name` tests, add backward-compat alias tests |
| `tests/test_utils/test_dispatch_models.py` | Remove `function_name`/`state_machine_name` from all LambdaResource/StepFunctionResource constructors |
| `tests/test_action/test_parse_payload.py` | Update matrix assertions: `function_name` -> `name` in matrix entries, `state_machine_name` -> `name` |
| `tests/test_action/test_deploy.py` | Replace `INPUT_FUNCTION_NAME` with `INPUT_RESOURCE_NAME` as the AWS function name |
| `tests/test_action/test_deploy_stepfunctions.py` | Replace `INPUT_STATE_MACHINE_NAME` with `INPUT_RESOURCE_NAME` as the AWS SM name |
| `tests/test_backend/test_dispatch_trigger.py` | Remove `function_name`/`state_machine_name` from resource construction |
| `tests/test_backend/test_handler.py` | Update any mock configs that include `function_name`/`state_machine_name` |
| `tests/test_backend/test_handler_pr.py` | Update mock configs |
| `tests/test_backend/test_handler_phase2.py` | Update mock configs |
| `tests/test_backend/test_handler_comment.py` | Update mock configs |
| `tests/test_backend/test_handler_push_env.py` | Update mock configs |
| `tests/test_backend/test_handler_workflow.py` | Update mock configs |

## Architecture Patterns

### Pattern 1: Backward-Compatible Alias via model_validator

Use Pydantic `model_validator(mode="before")` to silently accept old field names during migration. This is the standard Pydantic pattern for field deprecation.

```python
class LambdaConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    ecr_repo: str
    runtime: str = "python3.14"

    @model_validator(mode="before")
    @classmethod
    def handle_deprecated_function_name(cls, data: Any) -> Any:
        """Accept function_name as alias for name during migration."""
        if isinstance(data, dict) and "function_name" in data:
            # If function_name matches name (or name is absent), just drop it
            if "name" not in data:
                data["name"] = data.pop("function_name")
            else:
                # function_name present alongside name: drop it (name wins)
                data.pop("function_name")
        return data
```

**Key decision:** `extra="forbid"` is set on all models. Without the validator, a ferry.yaml with `function_name:` would fail validation. The validator must consume the field BEFORE Pydantic sees it.

### Pattern 2: Resource Name as Matrix Key

After simplification, the matrix entry uses `name` for both the display name AND the AWS resource name. The workflow template changes from:

```yaml
# Before
function-name: ${{ matrix.function_name }}

# After
function-name: ${{ matrix.name }}
```

But actually, we can eliminate the `function-name` input entirely from the composite action and just use `resource-name` as the AWS function name inside the deploy script. This is cleaner.

### Pattern 3: Deploy Scripts Use resource_name Directly

```python
# deploy.py main() -- AFTER
resource_name = os.environ["INPUT_RESOURCE_NAME"]
function_name = resource_name  # name IS the function name

# deploy_stepfunctions.py main() -- AFTER
resource_name = os.environ["INPUT_RESOURCE_NAME"]
state_machine_name = resource_name  # name IS the state machine name
```

### Anti-Patterns to Avoid

- **Don't add deprecation warnings to ferry.yaml parsing.** The project has no external users. Silent alias acceptance is sufficient.
- **Don't keep function_name/state_machine_name in dispatch payload models.** The backend controls dispatch -- simplify the payload too.
- **Don't change ApiGatewayConfig.** `rest_api_id` and `stage_name` are AWS identifiers, not names. They must remain separate fields.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Field aliasing | Custom YAML preprocessing | Pydantic `model_validator(mode="before")` | Handles all input paths (dict, JSON, YAML) |
| Schema migration | Version bump + migration script | Backward-compat validator | No external users, silent migration is fine |

## Common Pitfalls

### Pitfall 1: extra="forbid" Rejects Old Fields
**What goes wrong:** ferry.yaml with `function_name:` field fails Pydantic validation because `extra="forbid"` rejects unknown fields.
**Why it happens:** The field is removed from the model, but old configs still have it.
**How to avoid:** The `model_validator(mode="before")` runs BEFORE field validation. It must pop the deprecated field from the dict so Pydantic never sees it.
**Warning signs:** `ValidationError: ... Extra inputs are not permitted` in tests or E2E.

### Pitfall 2: Error Messages Still Reference Old Fields
**What goes wrong:** Error messages in deploy.py mention "ferry.yaml function_name" but that field no longer exists.
**Why it happens:** String literals in error handling code reference the old schema.
**How to avoid:** Search for all string occurrences of `function_name` and `state_machine_name` across the codebase and update error messages.
**Warning signs:** Grep for `function_name` in strings (not just code references).

### Pitfall 3: Workflow Template Not Updated in Sync
**What goes wrong:** The composite action removes the input, but the workflow template still passes it.
**Why it happens:** The workflow template is in `docs/setup.md` (docs) and the test repo (separate repo). Easy to forget one.
**How to avoid:** Checklist: (1) action.yml, (2) docs/setup.md template, (3) ferry-test-app ferry.yml.

### Pitfall 4: Test Assertions Still Check Old Field Names
**What goes wrong:** Tests pass construction of objects without `function_name` (because it was removed) but assertions still check for `function_name` in matrix output.
**Why it happens:** Matrix dict construction in parse_payload.py changes, but test assertions are scattered across many files.
**How to avoid:** Systematic grep for `function_name` and `state_machine_name` in test files after changes.

### Pitfall 5: StepFunctionConfig Backward Compat is Different
**What goes wrong:** LambdaConfig already defaults `function_name` to `name`, so the alias is straightforward. But `StepFunctionConfig.state_machine_name` is required with no default -- old configs that have `name: order-workflow` and `state_machine_name: OrderWorkflow` (different values) need special handling.
**Why it happens:** The current schema allows name and state_machine_name to be different.
**How to avoid:** When `state_machine_name` is present but `name` differs, the migration should use `state_machine_name` as the new `name` (since that's the AWS resource name). The validator should handle: if both present, set `name = state_machine_name` and drop `state_machine_name`. If only `name` present, use it directly.

### Pitfall 6: ferry-test-app Has Divergent Names
**What goes wrong:** The test app currently has `name: hello-world` but `function_name: ferry-test-hello-world`. Similarly SF has `name: hello-chain` but `state_machine_name: ferry-test-sf`. After migration, `name` must be the AWS resource name.
**Why it happens:** The old schema allowed display names and AWS names to diverge.
**How to avoid:** When migrating ferry-test-app, `name` must become the AWS resource name: `name: ferry-test-hello-world` (not `hello-world`). Same for SF: `name: ferry-test-sf`. This changes how the resource appears in plan/deploy comments.

## ferry-test-app Migration

Current ferry.yaml:
```yaml
lambdas:
  - name: hello-world
    source_dir: lambdas/hello-world
    ecr_repo: ferry-test/hello-world
    function_name: ferry-test-hello-world    # <-- REMOVE
    runtime: python3.12

step_functions:
  - name: hello-chain
    source_dir: workflows/hello-chain
    state_machine_name: ferry-test-sf        # <-- REMOVE
    definition_file: definition.json
```

After migration:
```yaml
lambdas:
  - name: ferry-test-hello-world             # <-- AWS function name
    source_dir: lambdas/hello-world
    ecr_repo: ferry-test/hello-world
    runtime: python3.12

step_functions:
  - name: ferry-test-sf                      # <-- AWS state machine name
    source_dir: workflows/hello-chain
    definition_file: definition.json
```

Also update `.github/workflows/ferry.yml`:
- Remove `function-name: ${{ matrix.function_name }}` from deploy-lambda job
- Remove `state-machine-name: ${{ matrix.state_machine_name }}` from deploy-step-function job

## Execution Order

The changes must be deployed in a specific order to avoid breaking the live system:

1. **Backend + ferry-utils first** (schema + dispatch models) -- deployed to Lambda
2. **ferry-action second** (parse_payload + deploy scripts + action.yml) -- referenced by @main
3. **ferry-test-app third** (ferry.yaml + ferry.yml) -- consumes the action

Since all three are in the same monorepo (except ferry-test-app), steps 1 and 2 deploy together. Step 3 is a separate push to the test repo.

**Critical ordering within ferry-action:** The composite action.yml files must update in sync with deploy.py changes. If action.yml removes the `function-name` input but deploy.py still reads `INPUT_FUNCTION_NAME`, deploys break.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | pyproject.toml (root) |
| Quick run command | `/Users/amit/Repos/github/ferry/.venv/bin/python -m pytest tests/ -x -q` |
| Full suite command | `/Users/amit/Repos/github/ferry/.venv/bin/python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01a | LambdaConfig.name used as AWS function name | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (needs update) |
| SCHEMA-01b | StepFunctionConfig.name used as state machine name | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (needs update) |
| SCHEMA-01c | ApiGatewayConfig keeps rest_api_id and stage_name | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (no change needed) |
| SCHEMA-01d | Deploy code uses .name instead of .function_name | unit | `.venv/bin/python -m pytest tests/test_action/ -x` | Exists (needs update) |
| SCHEMA-01e | Backward compat accepts old field names | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Needs new tests |
| SCHEMA-01f | Dispatch models simplified | unit | `.venv/bin/python -m pytest tests/test_utils/test_dispatch_models.py -x` | Exists (needs update) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/ -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -q`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. New backward-compat tests will be added as part of implementation.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: all source files read and analyzed
- `backend/src/ferry_backend/config/schema.py` -- current LambdaConfig, StepFunctionConfig models
- `utils/src/ferry_utils/models/dispatch.py` -- current LambdaResource, StepFunctionResource models
- `action/src/ferry_action/deploy.py` -- current Lambda deploy pipeline
- `action/src/ferry_action/deploy_stepfunctions.py` -- current SF deploy pipeline
- `action/src/ferry_action/parse_payload.py` -- current matrix builder
- `action/deploy/action.yml`, `action/deploy-stepfunctions/action.yml` -- composite action inputs
- `docs/setup.md` -- workflow template and ferry.yaml docs
- ferry-test-app `ferry.yaml` via GitHub API -- current test configuration

### Secondary (MEDIUM confidence)
- Pydantic v2 `model_validator` pattern -- confirmed from training data, consistent with existing codebase usage

## Metadata

**Confidence breakdown:**
- Impact analysis: HIGH -- every file was read and the full field flow is mapped
- Architecture patterns: HIGH -- using same Pydantic patterns already in the codebase
- Pitfalls: HIGH -- derived from actual divergent names in ferry-test-app and extra=forbid constraint
- Test coverage: HIGH -- all 443 existing tests enumerated, affected tests identified

**Research date:** 2026-03-14
**Valid until:** No expiry -- this is internal codebase analysis, not library version research
