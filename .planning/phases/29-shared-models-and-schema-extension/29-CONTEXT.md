# Phase 29 Context: Shared Models and Schema Extension

**Phase Goal:** Both backend and action can work with v3 dispatch payloads and environment-aware ferry.yaml configs
**Requirements:** COMPAT-01, ENV-01
**Created:** 2026-03-12

## Decisions

### 1. ferry.yaml environments syntax — Dict-keyed

Environments use the same dict-keyed pattern as resources (lambdas, step_functions, api_gateways). The YAML key is the environment name.

```yaml
version: 1
environments:
  staging:
    branch: develop
    auto_deploy: true
  production:
    branch: main
    auto_deploy: true
lambdas:
  order-processor:
    source: services/order-processor
    ecr: ferry/order-processor
```

**Rationale:** Consistent with existing ferry.yaml patterns. Dict keys naturally enforce unique environment names (duplicate YAML keys overwrite). Multiple environments can map to the same branch (e.g., different teams working on `develop`).

**No name validation** — trust the user to match their GitHub Environment name exactly. Ferry passes the name through; GHA validates it.

### 2. Schema version — Extend v2 in place

Keep `v: Literal[2]` on `BatchedDispatchPayload`. Add new fields with defaults directly to the existing model. No version bump, no new model class, no new parser branch.

**New fields on BatchedDispatchPayload:**
- `mode: str = "deploy"` — "deploy" for actual deployment, "plan" reserved for future use
- `environment: str = ""` — resolved environment name, empty string = no environment
- `head_ref: str = ""` — PR head branch name (for PR-triggered flows)
- `base_ref: str = ""` — PR base branch name (for PR-triggered flows)

**Rationale:** No external users running older payloads — we're still in dev. Adding fields with defaults means existing code continues working without changes. No need for a third parser branch in the action.

**>65KB fallback stays permanently.** This is a GitHub `workflow_dispatch` API platform limit (65,535 chars per input value), not a version concern. The per-type dispatch fallback must work with the new fields too.

### 3. auto_deploy field semantics

`auto_deploy: bool = True` on `EnvironmentMapping`. User controls per environment in ferry.yaml.

- `auto_deploy: true` — push to mapped branch triggers deploy dispatch (current behavior, now environment-aware)
- `auto_deploy: false` — push to mapped branch skips dispatch entirely. Deploy only via `/ferry apply` on a PR.
- No warning when auto_deploy is false and a merge happens — silent no-deploy is the intended configured behavior.

**Rationale:** Follows Digger pattern where behavior config lives in the project config file. Users decide per-environment whether pushes auto-deploy.

**Note:** Phase 29 defines the field in the model only. The push handler behavior change (checking `auto_deploy`) is implemented in Phase 32.

## Code Context

### Files to modify

| File | Change |
|------|--------|
| `backend/src/ferry_backend/config/schema.py` | Add `EnvironmentMapping` model; add `environments: dict[str, EnvironmentMapping]` to `FerryConfig` (parsed from dict-keyed YAML) |
| `utils/src/ferry_utils/models/dispatch.py` | Add `mode`, `environment`, `head_ref`, `base_ref` fields to `BatchedDispatchPayload` |
| `utils/src/ferry_utils/constants.py` | No change — `BATCHED_SCHEMA_VERSION` stays at 2 |
| `tests/test_backend/test_config_schema.py` | Tests for `EnvironmentMapping` parsing, `FerryConfig` with environments section |
| `tests/test_utils/test_dispatch_models.py` | Tests for new fields on `BatchedDispatchPayload`, default values |

### Existing patterns to follow

- All models: `ConfigDict(frozen=True, extra="forbid")`
- Config parsing: dict-keyed YAML → model with `name` set from key (see `LambdaConfig` pattern in `schema.py`)
- Payload fields: all new fields get safe defaults so existing payloads parse without changes
- Tests: follow existing test structure in `test_config_schema.py` and `test_dispatch_models.py`

### Model shapes (for downstream agents)

```python
# backend/src/ferry_backend/config/schema.py
class EnvironmentMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str          # set from dict key during parsing
    branch: str        # required — which branch maps to this environment
    auto_deploy: bool = True

class FerryConfig(BaseModel):
    # ... existing fields ...
    environments: list[EnvironmentMapping] = []
    # parsed from dict-keyed YAML via validator (same pattern as resources)
```

```python
# utils/src/ferry_utils/models/dispatch.py
class BatchedDispatchPayload(BaseModel):
    # ... existing fields (v, lambdas, step_functions, api_gateways, trigger_sha, deployment_tag, pr_number) ...
    mode: str = "deploy"
    environment: str = ""
    head_ref: str = ""
    base_ref: str = ""
```

## Deferred Ideas

- Per-environment resource overrides (e.g., environment-specific config) — v3+
- Branch glob patterns for environment mapping (e.g., `release/*`) — v3+
- Environment name validation against GitHub Environments API — not planned

---
*Context created: 2026-03-12*
