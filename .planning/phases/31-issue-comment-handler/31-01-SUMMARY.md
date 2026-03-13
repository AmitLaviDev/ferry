---
phase: 31-issue-comment-handler
plan: 01
subsystem: backend
tags: [webhook, issue-comment, workflow-run, apply, plan, dedup]
dependency_graph:
  requires: [29-01]
  provides: [issue-comment-handler, workflow-run-handler, apply-comment, command-parser]
  affects: [handler.py, plan.py, trigger.py, dedup.py]
tech_stack:
  added: []
  patterns: [command-parsing-regex, sha-specific-comment-marker, paginated-comment-search]
key_files:
  created:
    - tests/test_backend/test_handler_comment.py
    - tests/test_backend/test_handler_workflow.py
  modified:
    - backend/src/ferry_backend/checks/plan.py
    - backend/src/ferry_backend/webhook/handler.py
    - backend/src/ferry_backend/webhook/dedup.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - tests/test_backend/test_plan.py
    - tests/test_backend/test_handler_pr.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_backend/test_dedup.py
decisions:
  - Non-sticky plan comments (POST not upsert) for both PR events and /ferry plan commands
  - Apply comments use SHA-specific markers (<!-- ferry:apply:{sha} -->) for targeted updates
  - Rocket reaction added before any processing (even on closed PRs)
  - structlog event kwarg conflict resolved by renaming to trigger_event
metrics:
  duration: 9m31s
  completed: 2026-03-13
  tasks: 2/2
  tests_added: 41 (plan.py) + 13 (comment) + 7 (workflow) + 2 (trigger) + 8 (dedup) = 71
  tests_total: 226
---

# Phase 31 Plan 01: Issue Comment Handler and Deploy Dispatch Summary

Command parser, issue_comment handler, and workflow_run status updater with non-sticky plan comments and environment-aware deploy dispatch.

## What Was Done

### Task 1: Update plan.py (a4b794e)

Removed sticky plan comment infrastructure and added command parsing and apply comment functions.

**Removed:**
- `PLAN_MARKER` constant (`<!-- ferry:plan -->`)
- `find_plan_comment()` -- paginated search for sticky marker
- `upsert_plan_comment()` -- create-or-update pattern

**Added:**
- `parse_ferry_command()` -- regex parser for `/ferry plan|apply` (case-insensitive, leading whitespace tolerant)
- `APPLY_MARKER_TEMPLATE` -- `<!-- ferry:apply:{sha} -->` for SHA-specific apply comments
- `format_apply_comment()` -- deploy-triggered comment with resource count, environment, waiting line
- `format_apply_status_update()` -- replaces waiting line with conclusion emoji and run link
- `find_apply_comment()` -- paginated search for SHA-specific apply marker

**Updated:**
- `format_plan_comment()` -- removed PLAN_MARKER from output (header is first line)
- `format_no_changes_comment()` -- removed PLAN_MARKER from output

### Task 2: Update trigger.py, handler.py, dedup.py (9cae76b)

Added environment forwarding to dispatch payloads, issue_comment and workflow_run event routing, and converted PR handler to non-sticky comments.

**trigger.py:**
- Added keyword-only args: `mode`, `environment`, `head_ref`, `base_ref`
- These flow into `BatchedDispatchPayload` constructor
- Existing callers work unchanged (backward-compatible defaults)

**handler.py:**
- Extended event filter: `{"push", "pull_request", "issue_comment", "workflow_run"}`
- Added `_handle_issue_comment()`: parses command, guards (PR-only, open state), adds rocket reaction, routes to plan/apply
- Added `_handle_plan_command()`: posts new plan comment + check run
- Added `_handle_apply_command()`: dispatches with environment, posts apply comment + check run
- Added `_handle_workflow_run()`: filters for Ferry dispatch runs, fetches inputs, finds apply comment, PATCHes with conclusion
- Converted `_handle_pull_request()`: uses `post_pr_comment()` instead of `upsert_plan_comment()`, always posts new comment (non-sticky)

**dedup.py:**
- Added `issue_comment` dedup key: `EVENT#issue_comment#{repo}#{comment_id}`
- Added `workflow_run` dedup key: `EVENT#workflow_run#{repo}#{run_id}`
- Both checked before existing `pull_request` and `push` patterns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] structlog `event` kwarg conflict**
- **Found during:** Task 2 GREEN phase
- **Issue:** `log.info("workflow_run_not_dispatch", event=wf_run.get("event"))` failed because `event` is a reserved positional arg in structlog
- **Fix:** Renamed kwarg to `trigger_event`
- **Files modified:** backend/src/ferry_backend/webhook/handler.py
- **Commit:** 9cae76b

## Decisions Made

1. **Non-sticky plan comments**: Each PR event or `/ferry plan` creates a new comment instead of updating an existing one. Simpler, avoids race conditions with concurrent pushes.
2. **SHA-specific apply markers**: `<!-- ferry:apply:{sha} -->` uniquely identifies which deploy a status update belongs to, preventing cross-SHA updates.
3. **Rocket reaction before guards**: Reaction is posted even when the PR is closed, giving immediate visual feedback that Ferry received the command.
4. **Fresh head SHA from API**: `/ferry apply` always fetches the current PR head SHA via `GET /pulls/{number}` to avoid deploying stale code.

## Test Results

```
226 passed in 3.50s
```

All tests pass including 71 new tests:
- test_plan.py: 41 tests (was 30 -- removed 19 old sticky tests, added 30 new)
- test_handler_comment.py: 13 tests (new file)
- test_handler_workflow.py: 7 tests (new file)
- test_dispatch_trigger.py: 25 tests (was 23 -- added 2 environment forwarding)
- test_dedup.py: 19 tests (was 11 -- added 8 issue_comment/workflow_run/isolation)
- test_handler_pr.py: 11 tests (was 12 -- updated for non-sticky)

## Self-Check: PASSED

All 10 key files verified present. Both task commits (a4b794e, 9cae76b) verified in git log. 226 tests passing.
