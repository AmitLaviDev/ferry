# Phase 6: Fix Lambda function_name Pipeline - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the DEPLOY-01 integration break: `function_name` exists in `LambdaConfig` (backend) and is consumed by `deploy.py` (action via `INPUT_FUNCTION_NAME`), but is missing from the dispatch model (`LambdaResource`) that connects them. Wire `function_name` through the full pipeline: ferry.yaml -> LambdaConfig -> LambdaResource -> parse_payload -> deploy.py.

</domain>

<decisions>
## Implementation Decisions

### Dispatch payload shape
- Add `function_name` as a **new required field** on `LambdaResource`, alongside existing `name`
- `name` = resource key for identification in the dispatch payload; `function_name` = AWS Lambda target
- `function_name` is always a resolved `str` (never None) by the time it reaches `LambdaResource`
- `parse_payload.py` surfaces only `function_name` to the GHA matrix (as `INPUT_FUNCTION_NAME`); `name` is not passed to the action
- **Scope:** Only wire `function_name` — do NOT add `runtime` to LambdaResource (Phase 7 handles runtime)

### Default resolution
- Backend resolves defaults: `LambdaConfig`'s existing `model_validator` defaults `function_name` to `name`
- `_build_resource` in `trigger.py` reads the already-resolved `function_name` from `LambdaConfig`
- No validation of AWS Lambda naming rules on `function_name` — let AWS reject invalid names at deploy time
- Single source of truth: backend resolves, action trusts the value

### Error handling contract
- **Missing function_name:** `deploy.py` fails fast with clear message if `INPUT_FUNCTION_NAME` is missing or empty — no fallback, no guessing
- **Function not found:** Error message includes the function_name that was tried AND suggests possible cause: "Lambda function 'X' not found. Check ferry.yaml function_name or verify the Lambda exists in the target account."

### Claude's Discretion
- Test structure and assertion patterns
- Exact error message wording (following the patterns above)
- Whether to add function_name to existing test fixtures or create new ones

</decisions>

<specifics>
## Specific Ideas

- The gap is well-characterized: LambdaConfig has function_name, deploy.py reads INPUT_FUNCTION_NAME, but LambdaResource in the middle doesn't carry it
- Four touch points: LambdaResource model, _build_resource in trigger.py, parse_payload.py matrix output, deploy.py env var reading

</specifics>

<deferred>
## Deferred Ideas

- Wiring `runtime` through the same pipeline path — Phase 7 (tech debt cleanup)
- AWS naming validation on function_name — future enhancement if user demand

</deferred>

---

*Phase: 06-fix-lambda-function-name-pipeline*
*Context gathered: 2026-02-27*
