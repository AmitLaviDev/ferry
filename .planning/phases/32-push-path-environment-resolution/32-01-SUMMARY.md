---
phase: 32-push-path-environment-resolution
plan: 01
subsystem: backend/webhook
tags: [push-handler, environment-gating, dispatch, check-run]
dependency_graph:
  requires: [phase-29-shared-models]
  provides: [environment-gated-push-dispatch, early-return-deleted-tags]
  affects: [handler.py, test_handler_phase2.py, REQUIREMENTS.md]
tech_stack:
  added: []
  patterns: [environment-gated-dispatch, early-return-before-auth]
key_files:
  created:
    - tests/test_backend/test_handler_push_env.py
  modified:
    - backend/src/ferry_backend/webhook/handler.py
    - tests/test_backend/test_handler_phase2.py
    - .planning/REQUIREMENTS.md
decisions:
  - "Removed is_default_branch gate entirely, replaced with resolve_environment()"
  - "All pushes use before_sha as compare base (incremental diff), not default_branch"
  - "Branch deletions and tag pushes return before auth step (zero API calls)"
  - "Unmapped branches produce zero Ferry activity (no check run, no dispatch)"
  - "ENV-03 updated: no environments = no push deploys (breaking change from v1.x)"
metrics:
  duration: 8min
  completed: 2026-03-13
---

# Phase 32 Plan 01: Push Path Environment Resolution Summary

Environment-gated push dispatch replacing is_default_branch gate with resolve_environment(), early returns for deleted branches/tags, and 7 integration tests.

## What Was Done

### Task 1: Write integration tests (TDD RED)
Created `tests/test_backend/test_handler_push_env.py` with 7 tests in `TestPushEnvironment`:
1. `test_mapped_branch_auto_deploy_dispatches` - push to main with production mapping triggers dispatch with environment="production"
2. `test_environment_name_in_dispatch_payload` - push to develop with staging mapping verifies environment="staging" in payload
3. `test_auto_deploy_false_silent` - push to mapped branch with auto_deploy: false produces zero dispatch and check run
4. `test_unmapped_branch_silent` - push to feature-xyz with only main mapping produces zero activity
5. `test_no_environments_silent` - push with no environments section produces zero activity
6. `test_branch_deletion_ignored` - deleted: true returns "ignored" before auth, zero API calls
7. `test_tag_push_ignored` - refs/tags/v1.0 returns "ignored" before auth, zero API calls

All 7 tests confirmed RED (failing) against the old handler code.

### Task 2: Refactor push handler + update ENV-03 (TDD GREEN)
Three areas modified in `handler.py`:

**Area 1: Early returns before auth** - Branch deletions (deleted: true) and tag pushes (refs/tags/) now return immediately after signature validation, before any GitHub API calls.

**Area 2: Compare base simplification** - Removed the `is_default_branch` ternary for compare base. All pushes now use `before_sha` (incremental diff). The old `default_branch` compare base was for PR branch check runs, which the pull_request handler now covers.

**Area 3: Environment-gated dispatch** - Replaced the `if is_default_branch and affected: dispatch` block with `resolve_environment(config, branch)` -> check `auto_deploy` -> dispatch with `mode="deploy"`, `environment=name`, `head_ref`, `base_ref`. Check Run created for all auto_deploy matched branches.

Updated 6 existing phase 2 tests to reflect new behavior:
- Default branch tests: added environments to ferry.yaml config and check run mock
- Feature branch tests: updated to verify unmapped branches are silent (no check run)
- Compare base test: changed to verify incremental diff (before_sha, not default_branch)

Updated ENV-03 in REQUIREMENTS.md from "deploys without environment (v1.x behavior)" to "pushes produce no Ferry activity".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated 6 existing phase 2 tests for new behavior**
- **Found during:** Task 2
- **Issue:** Existing tests assumed old is_default_branch behavior (default branch always dispatches without environments, feature branches create check runs)
- **Fix:** Updated ferry.yaml fixtures to include environments, adjusted assertions for unmapped branch silence, changed compare base expectations
- **Files modified:** tests/test_backend/test_handler_phase2.py
- **Commit:** d15ed13

## Verification

1. New tests green: 7/7 passed
2. Existing handler tests green: 10/10 passed
3. Full test suite green: 429/429 passed
4. ENV-03 updated in REQUIREMENTS.md: confirmed "no Ferry activity" wording
5. resolve_environment used in push handler: line 218 of handler.py
6. is_default_branch fully removed: zero matches in handler.py

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | a7906b4 | test(32-01): add failing tests for environment-gated push dispatch |
| 2 (GREEN) | d15ed13 | feat(32-01): implement environment-gated push dispatch |
