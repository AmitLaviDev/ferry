# Phase 33 Context: Action v3 Parsing and Outputs

**Phase Goal:** The ferry setup action exposes mode and environment as workflow outputs so downstream jobs can consume them.
**Requirements:** COMPAT-02
**Created:** 2026-03-13

## Decisions

### 1. Outputs: mode and environment only (no head_ref/base_ref)

The setup action adds two new GHA outputs: `mode` and `environment`. The `head_ref` and `base_ref` fields from the payload are NOT exposed as outputs — add them later if/when the workflow template needs them.

**Rationale:** Minimal surface area. Phase 34 (workflow template) only needs mode for deploy guards and environment for GitHub Environment injection. head_ref/base_ref are informational — add when there's a concrete consumer.

### 2. Add mode and environment to v1 DispatchPayload

Add `mode: str = "deploy"` and `environment: str = ""` to the v1 `DispatchPayload` model. This ensures the >65KB fallback path preserves mode/environment information when the backend falls back from batched v2 to per-type v1 dispatch.

**Rationale:** The >65KB fallback is a permanent feature (GitHub platform limit). Without these fields on v1, a `/ferry apply` dispatch that exceeds 65KB would lose the environment name — breaking the deployment.

**Fields to add to `DispatchPayload`:**
```python
mode: str = "deploy"
environment: str = ""
```

### 3. v1 parser extracts mode/environment from payload

`_parse_v1()` reads `mode` and `environment` from the parsed `DispatchPayload` model (not hardcoded defaults). Since the model has defaults, old v1 payloads (without these fields) still parse correctly with `mode="deploy"` and `environment=""`.

**Rationale:** Now that v1 carries these fields, the parser should read them. Hardcoding defaults would silently discard valid data from the >65KB fallback path.

## Prior Decisions (locked from phases 29/30/31/32)

- v2 schema extended in place, no version bump — `v: Literal[2]` stays (phase 29)
- `BatchedDispatchPayload` already has `mode`, `environment`, `head_ref`, `base_ref` fields (phase 29)
- Plan mode never dispatches — the action only ever sees `mode="deploy"` (phase 30)
- Environment resolved from branch mapping by backend before dispatch (phases 31/32)
- mode guard on deploy jobs is phase 34's concern, not phase 33's

## Code Context

### Files to modify

| File | Change |
|------|--------|
| `utils/src/ferry_utils/models/dispatch.py` | Add `mode: str = "deploy"` and `environment: str = ""` to `DispatchPayload` |
| `action/src/ferry_action/parse_payload.py` | Add `mode` and `environment` to `ParseResult`; extract from payload in `_parse_v1()` and `_parse_v2()`; output in `main()` |
| `tests/test_action/test_parse_payload.py` | Tests for new outputs with v1 and v2 payloads, backward compatibility |
| `tests/test_utils/test_dispatch_models.py` | Tests for new fields on `DispatchPayload` |

### Existing patterns to follow

- `ParseResult` is a frozen dataclass — add `mode: str` and `environment: str` fields
- `main()` uses `set_output()` for each field — add two more calls
- `_parse_v2()` reads fields from `BatchedDispatchPayload` — `payload.mode`, `payload.environment`
- `_parse_v1()` reads fields from `DispatchPayload` — same pattern
- Tests: `_make_batched_payload()` helper already exists; extend `_make_payload()` to accept mode/environment

### ParseResult shape (for downstream agents)

```python
@dataclass(frozen=True)
class ParseResult:
    lambda_matrix: dict
    sf_matrix: dict
    ag_matrix: dict
    has_lambdas: bool
    has_step_functions: bool
    has_api_gateways: bool
    resource_types: str
    mode: str           # NEW — "deploy" (only value for now)
    environment: str    # NEW — resolved environment name, "" = no environment
```

### New GHA outputs

| Output | Source (v2) | Source (v1) | Default |
|--------|-------------|-------------|---------|
| `mode` | `payload.mode` | `payload.mode` | `"deploy"` |
| `environment` | `payload.environment` | `payload.environment` | `""` |

## Deferred Ideas

- **Per-resource status in apply comment**: When `/ferry apply` triggers a deploy, show a table of resources with status emojis (hourglass while running, checkmark on success, X on failure). Requires per-job status tracking via workflow_run, not just aggregate conclusion. Nice UX improvement for a future phase.
- **head_ref/base_ref as GHA outputs**: Add when workflow template has a concrete use case (e.g., deploy job summaries showing source branch).

---
*Context created: 2026-03-13*
