---
phase: 36-pr-comment-ux-polish
plan: 01
subsystem: backend
tags: [ux, pr-comments, deploy-status]
dependency_graph:
  requires: [35-01]
  provides: [table-format-plan, sticky-deploy-comment, sha-mismatch-protection]
  affects: [checks/plan.py, checks/runs.py, webhook/handler.py]
tech_stack:
  added: []
  patterns: [sticky-comment-upsert, sha-marker-correlation, table-format-comments]
key_files:
  created: []
  modified:
    - backend/src/ferry_backend/checks/plan.py
    - backend/src/ferry_backend/checks/runs.py
    - backend/src/ferry_backend/webhook/handler.py
    - tests/test_backend/test_plan.py
    - tests/test_backend/test_handler_pr.py
    - tests/test_backend/test_handler_comment.py
    - tests/test_backend/test_handler_workflow.py
    - tests/test_backend/test_handler_phase2.py
    - tests/test_backend/test_handler_push_env.py
decisions:
  - "Display names changed from plural (Lambdas) to singular (Lambda) for table Type column"
  - "Deploy marker keyed on PR number, not SHA -- enables sticky comment pattern"
  - "SHA marker embedded in comment body for workflow_run correlation and race protection"
metrics:
  tasks_completed: 9
  tasks_total: 9
  test_count: 443
  test_pass: 443
  files_modified: 9
  completed: "2026-03-14"
---

# Phase 36 Plan 01: PR Comment UX Polish Summary

Table-format plan comments with resource details, sticky deploy comment with per-resource status table, SHA mismatch race protection on workflow_run updates.

## What Changed

### checks/plan.py
- Added `_TYPE_ORDER` dict and `_resource_detail()` helper for type-specific detail strings
- Changed `_TYPE_DISPLAY_NAMES` from plural ("Lambdas") to singular ("Lambda") for table column
- Rewrote `format_plan_comment()` -- now takes optional `config` parameter, outputs markdown table instead of grouped bullet lists
- Updated footer text to mention `/ferry apply` and merge as deployment options
- Replaced `APPLY_MARKER_TEMPLATE` with `DEPLOY_MARKER_TEMPLATE` (PR-level) and `SHA_MARKER_TEMPLATE` (SHA-level)
- Rewrote `format_apply_comment()` -- now takes `pr_number` and `config`, outputs resource status table with hourglass emojis
- Rewrote `format_apply_status_update()` -- updates header (Deploying -> Deployed/Failed), replaces hourglass with conclusion emoji, appends result line
- Replaced `find_apply_comment()` with `find_deploy_comment()` -- searches by PR number, not SHA
- Added `extract_sha_from_comment()` -- extracts trigger SHA from embedded marker

### checks/runs.py
- Added `update_pr_comment()` helper for PATCH-ing existing comments

### webhook/handler.py
- Updated imports to use new function names
- `_handle_pull_request` now passes `config` to `format_plan_comment`
- `_handle_plan_command` now takes `config` parameter and passes it to formatter
- `_handle_apply_command` now uses upsert pattern (find_deploy_comment -> update or create)
- `_handle_workflow_run` now uses `find_deploy_comment` + `extract_sha_from_comment` with SHA mismatch protection
- Push handler now calls `find_merged_pr` after dispatch and creates/updates deploy comment on merged PR

## New Functions

| Function | File | Purpose |
|----------|------|---------|
| `_resource_detail()` | checks/plan.py | Look up type-specific detail string for resource table |
| `find_deploy_comment()` | checks/plan.py | Find sticky deploy comment by PR number marker |
| `extract_sha_from_comment()` | checks/plan.py | Extract trigger SHA from embedded comment marker |
| `update_pr_comment()` | checks/runs.py | PATCH an existing PR comment |

## Test Coverage

- **test_plan.py**: 44 tests (rewritten for table format, deploy markers, SHA extraction)
- **test_handler_pr.py**: 11 tests (updated footer assertion)
- **test_handler_comment.py**: 14 tests (added upsert deploy comment test, deploy comment search mocks)
- **test_handler_workflow.py**: 8 tests (rewritten for deploy marker, added SHA mismatch test)
- **test_handler_phase2.py**: 10 tests (added second find_merged_pr mock for push handler)
- **test_handler_push_env.py**: 7 tests (added second find_merged_pr mock for push handler)
- **Total**: 443 tests, all passing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Push handler tests needed additional mock for find_merged_pr**
- **Found during:** Task 9 (full test suite run)
- **Issue:** Push handler now calls `find_merged_pr` after dispatch, which hits the same `/commits/{sha}/pulls` endpoint already consumed by `find_open_prs`. Tests in `test_handler_phase2.py` and `test_handler_push_env.py` failed with unmatched requests.
- **Fix:** Added second `_mock_prs_for_commit()` call in 5 test methods across 2 test files.
- **Files modified:** tests/test_backend/test_handler_phase2.py, tests/test_backend/test_handler_push_env.py
- **Commit:** f111a56

**2. [Rule 1 - Bug] SHA mismatch test used non-hex SHA string**
- **Found during:** Task 8 (workflow handler tests)
- **Issue:** Test `test_sha_mismatch_skips_update` used `"different_sha_999"` which contains underscores. The `_SHA_MARKER_RE` regex only matches `[a-f0-9]+`, so `extract_sha_from_comment` returned `None` instead of the SHA, causing the mismatch check to be skipped.
- **Fix:** Changed test SHA to `"def456def456789"` (valid hex).
- **Files modified:** tests/test_backend/test_handler_workflow.py
- **Commit:** f111a56

**3. [Rule 1 - Bug] Line too long in plan.py footer string**
- **Found during:** Task 9 (pre-commit hook)
- **Issue:** Footer string `"_Deploy with /ferry apply. Manual deployment to **{environment.name}** after merge._"` exceeded 100 chars.
- **Fix:** Extracted `environment.name` to local variable `env` to shorten the line.
- **Files modified:** backend/src/ferry_backend/checks/plan.py
- **Commit:** f111a56
