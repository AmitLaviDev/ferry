---
phase: 33-action-v3-parsing-and-outputs
plan: 01
subsystem: action
tags: [parsing, outputs, backward-compat, pydantic, dataclass]
dependency_graph:
  requires: []
  provides: [mode-output, environment-output]
  affects: [action/setup, utils/models]
tech_stack:
  added: []
  patterns: [pydantic-field-extension, frozen-dataclass-extension, set-output-wiring]
key_files:
  created: []
  modified:
    - utils/src/ferry_utils/models/dispatch.py
    - action/src/ferry_action/parse_payload.py
    - action/setup/action.yml
    - tests/test_utils/test_dispatch_models.py
    - tests/test_action/test_parse_payload.py
decisions:
  - "Read mode/environment from payload model (not hardcoded defaults) in both v1 and v2 parsers"
  - "head_ref/base_ref NOT added to v1 DispatchPayload (deferred per CONTEXT.md)"
metrics:
  duration: 202s
  completed: "2026-03-13T14:57:12Z"
  tasks: 2
  files: 5
requirements: [COMPAT-02]
---

# Phase 33 Plan 01: Action v3 Parsing and Outputs Summary

Extended DispatchPayload with mode/environment defaults, wired through ParseResult and main() to GHA outputs, with full v1/v2 backward compatibility.

## What Was Done

### Task 1: Write Failing Tests (TDD RED)
- Updated `test_v1_payload_still_unchanged` to assert `payload.mode == "deploy"` and `payload.environment == ""` instead of `not hasattr`
- Added 3 new model tests: `test_v1_payload_mode_defaults`, `test_v1_payload_mode_explicit`, `test_v1_payload_mode_from_json`
- Added 4 new parse tests: `test_v1_parse_mode_defaults`, `test_v1_parse_mode_explicit`, `test_v2_parse_mode_defaults`, `test_v2_parse_mode_explicit`
- Updated 2 main() tests to assert 9 output lines (up from 7) and check mode/environment values
- Added 2 new main() tests: `test_main_v1_explicit_mode_environment`, `test_main_v2_explicit_mode_environment`
- Extended `_make_payload()` and `_make_batched_payload()` helpers with optional mode/environment params
- **Commit:** 42e335c

### Task 2: Implement mode/environment (GREEN)
- Added `mode: str = "deploy"` and `environment: str = ""` to `DispatchPayload` model
- Added `mode: str` and `environment: str` fields to `ParseResult` dataclass
- Forwarded `payload.mode` and `payload.environment` in both `_parse_v1()` and `_parse_v2()`
- Added `set_output("mode", ...)` and `set_output("environment", ...)` calls in `main()`
- Declared `mode` and `environment` outputs in `action/setup/action.yml`
- **Commit:** b3cdb74

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- Targeted tests: 77 passed (0 failed)
- Full test suite: 438 passed (0 failed, 0 regressions)
- DispatchPayload has mode/environment fields with defaults
- ParseResult has mode/environment fields
- action.yml declares mode and environment outputs
- head_ref/base_ref only in BatchedDispatchPayload (not v1)

## Decisions Made

1. **Read from model, not hardcoded:** Both `_parse_v1()` and `_parse_v2()` read `payload.mode` and `payload.environment` rather than returning hardcoded defaults, so the >65KB fallback path preserves real values.
2. **head_ref/base_ref deferred:** Per CONTEXT.md, only mode and environment were added to v1 DispatchPayload. The `not hasattr` assertions for head_ref and base_ref were preserved in the guard-rail test.

## Self-Check: PASSED

All 6 files verified present. Both commits (42e335c, b3cdb74) verified in git log.
