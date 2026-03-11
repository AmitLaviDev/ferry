# Phase 26 Context: Backend Batched Dispatch

## Decisions

### 1. Fallback behavior on payload-size exceeded
- Client-side size check only (`len(payload_json) > 65535`) — no server-side retry
- On fallback: log a structured warning (`dispatch_fallback_to_per_type` with payload size), then dispatch per-type v1 payloads
- Fallback is explicit in logs but NOT in the return value — return shape stays the same as normal per-type results
- Fallback uses actual v1 `DispatchPayload` wire format (not v2 single-type batched payloads) — proven, action already handles it
- Extract v1 per-type loop into a `_dispatch_per_type()` helper; main function body is the v2 batched path

### 2. Return value / caller contract
- Return shape is unchanged: `list[dict]` with one entry per resource type, each `{"type": str, "status": int, "workflow": str}`
- Batched dispatch: expand into one entry per type included in the batch (all share the same status code from the single API call)
- Fallback dispatch: normal per-type entries (identical to v1 behavior)
- Handler (`handler.py`) requires zero changes — return shape is stable across both paths
- Logging: one `dispatch_triggered` log event per type included, with `mode="batched"` field added

### 3. Backward compatibility / rollout
- No toggle, no feature flag, no env var — ship v2 as the only path
- No rollout concerns — test repo is the only consumer, project is unpublished
- Deploy backend and action together (Phases 26+27 go live at same time via Phase 28 E2E)
- v1 `DispatchPayload` model kept as-is in ferry-utils (used by fallback path + action parsing)
- v1 per-type dispatch path exists solely as the >65KB payload-size fallback

## Code Context

### Files to modify
- `backend/src/ferry_backend/dispatch/trigger.py` — Main change: replace per-type loop with batched dispatch, extract `_dispatch_per_type()` helper for fallback
- Imports: add `BatchedDispatchPayload`, `BATCHED_SCHEMA_VERSION` from ferry-utils

### Files unchanged
- `backend/src/ferry_backend/webhook/handler.py` — Zero changes, return contract is stable
- `utils/src/ferry_utils/models/dispatch.py` — Phase 25 already added the v2 model

### Key function: `trigger_dispatches()` new flow
```
1. Group affected resources by type (same as today)
2. Build typed resource lists for each type
3. Build BatchedDispatchPayload (v2) with all types
4. Serialize and check size
5. If <= 65KB: single dispatch, expand results per type
6. If > 65KB: log warning, call _dispatch_per_type() with v1 payloads
```

### Existing code reference
- `trigger.py` current structure: lines 103-184, per-type loop with DispatchPayload v1
- `_build_resource()` (lines 51-100): reusable as-is for both paths
- `_MAX_PAYLOAD_SIZE = 65535`: reuse existing constant

## Deferred Ideas
None captured during discussion.

---
*Created: 2026-03-11*
