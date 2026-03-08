---
phase: 18-tech-debt-cleanup
plan: 01
subsystem: action
tags: [tech-debt, error-handling, deploy, build]
dependency_graph:
  requires: []
  provides: [clean-error-output, context-aware-iam-hints, suppressed-docker-warnings]
  affects: [ferry-action-deploy, ferry-action-build]
tech_stack:
  added: []
  patterns: [context-aware-error-mapping, stderr-suppression]
key_files:
  created: []
  modified:
    - action/src/ferry_action/deploy.py
    - action/src/ferry_action/build.py
    - tests/test_action/test_deploy.py
    - tests/test_action/test_build.py
decisions:
  - "AccessDeniedException mapping uses message inspection (not error code subclasses) to distinguish caller vs target role"
  - "Generic AccessDeniedException mentions both possible causes rather than guessing"
metrics:
  duration: 219s
  completed: 2026-03-08
---

# Phase 18 Plan 01: Action Code Tech Debt (TD-01, TD-04, TD-05) Summary

Remove debug raw error output from deploy.py, distinguish caller vs target role in AccessDeniedException hints, and suppress Docker credential store warning in ECR login.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix deploy.py error handling (TD-01 + TD-05) | 60aab36 (tests), f2c7477 (impl) | deploy.py, test_deploy.py |
| 2 | Suppress Docker credential warning (TD-04) | 3acfacb | build.py, test_build.py |

## Changes Made

### Task 1: deploy.py Error Handling (TD-01 + TD-05)

**TD-01 -- Remove raw error output:** Removed the `raw = f"[{error_code}] {error_message}"` line and the `(raw: {raw})` suffix from `gha.error()`. The `format_error_detail` function already provides full tracebacks when `FERRY_DEBUG=1`, so the raw output was redundant and leaked internal error details in production.

**TD-05 -- Context-aware AccessDeniedException hints:** Replaced the single generic "IAM role lacks lambda:UpdateFunctionCode" hint with message inspection:
- "not authorized to perform" in message -> hint about deploy role (caller) lacking permissions
- "cannot be assumed" or "role defined for the function" in message -> hint about Lambda execution role trust policy
- Generic/empty message -> combined hint mentioning both possibilities

**Tests added:** `TestErrorMapping` class with 4 tests (caller role, target role, generic, no-raw-output) plus `test_resource_not_found_hint_unchanged` in `TestMain`.

### Task 2: Docker Credential Warning Suppression (TD-04)

Added `capture_output=True` to the `docker login` subprocess call in `ecr_login()`. This captures stderr (where Docker prints "WARNING! Your password will be stored unencrypted...") without affecting error detection since `check=True` still raises on non-zero exit.

**Test added:** `test_ecr_login_suppresses_stderr` verifying `capture_output=True` is passed.

## Verification Results

- 36/36 tests pass (22 deploy + 14 build)
- Ruff lint: 0 errors on both modified source files

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

- All 5 files verified present on disk
- All 3 commits verified in git log (60aab36, f2c7477, 3acfacb)
