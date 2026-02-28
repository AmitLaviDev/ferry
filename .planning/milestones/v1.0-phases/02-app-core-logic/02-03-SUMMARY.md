---
phase: 02-app-core-logic
plan: 03
subsystem: dispatch
tags: [workflow-dispatch, check-runs, github-api, orchestration, pipeline]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: GitHubClient, generate_app_jwt, get_installation_token, Settings, DispatchPayload, ResourceType
  - phase: 02-app-core-logic/plan-01
    provides: fetch_ferry_config, parse_config, validate_config, FerryConfig models
  - phase: 02-app-core-logic/plan-02
    provides: get_changed_files, match_resources, detect_config_changes, merge_affected, AffectedResource
provides:
  - trigger_dispatches function (one workflow_dispatch per resource type)
  - build_deployment_tag function (pr-N or branch-sha7 format)
  - create_check_run function (Terraform-plan-like deployment preview Check Runs)
  - format_deployment_plan function (markdown-formatted resource grouping)
  - find_open_prs function (filter commits/{sha}/pulls by state=open)
  - Complete Phase 2 webhook handler pipeline (auth -> config -> detect -> dispatch/check run)
affects: [03-build-and-deploy, 05-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [one-dispatch-per-type grouping, Terraform-plan-like Check Run formatting, merge-base comparison for PR branches, config diff on ferry.yaml change detection]

key-files:
  created:
    - backend/src/ferry_backend/dispatch/__init__.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - backend/src/ferry_backend/checks/__init__.py
    - backend/src/ferry_backend/checks/runs.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_backend/test_check_runs.py
    - tests/test_backend/test_handler_phase2.py
  modified:
    - backend/src/ferry_backend/webhook/handler.py
    - tests/test_backend/test_handler.py

key-decisions:
  - "GitHubClient at module level for Lambda cold start, auth methods called per-invocation"
  - "Merge-base comparison (default_branch...head) for PR branches; before...after for default branch"
  - "find_open_prs for both PR identification and merged-PR number lookup on default branch"
  - "Config diff triggered only when ferry.yaml is in changed_files list"
  - "Payload size check (65535 limit) with skip-and-log-error behavior"

patterns-established:
  - "Dispatch grouping: group AffectedResource by resource_type -> one DispatchPayload per group"
  - "Config-to-dispatch field mapping: source_dir -> source, ecr_repo -> ecr via _build_resource"
  - "Check Run formatting: ~ for modified, + for new, grouped by type with section headers"
  - "Handler pipeline: auth -> config -> detect -> branch-dependent dispatch/check-run"
  - "Phase 1 handler tests mock generate_app_jwt and provide minimal API mocks for Phase 2 passthrough"

requirements-completed: [DETECT-02, ORCH-01, ORCH-02]

# Metrics
duration: 9min
completed: 2026-02-24
---

# Phase 02 Plan 03: Dispatch & Orchestration Summary

**Workflow dispatch triggering (one per resource type), Terraform-plan-like PR Check Runs, and full Phase 2 handler pipeline wiring auth through config through detection to dispatch**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-24T15:44:58Z
- **Completed:** 2026-02-24T15:54:47Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- trigger_dispatches fires exactly one workflow_dispatch per affected resource type with DispatchPayload serialized as JSON input
- create_check_run posts "Ferry: Deployment Plan" Check Run with Terraform-plan-like formatting (~ modified, + new, grouped by type)
- Handler processes complete pipeline: authenticate -> fetch config -> detect changes -> dispatch (default branch) or check run (PR branches)
- Merge-base comparison for PR branches ensures Check Run shows ALL affected resources, not just incremental
- Config errors produce failed Check Runs with error details (not silent failures)
- 100 total backend tests passing with zero ruff lint errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Dispatch triggering and Check Run creation modules** - `d7e2e0c` (feat)
2. **Task 2: Wire complete Phase 2 pipeline into webhook handler** - `29f3c31` (feat)

## Files Created/Modified
- `backend/src/ferry_backend/dispatch/__init__.py` - Package init for dispatch module
- `backend/src/ferry_backend/dispatch/trigger.py` - build_deployment_tag, _build_resource, trigger_dispatches
- `backend/src/ferry_backend/checks/__init__.py` - Package init for checks module
- `backend/src/ferry_backend/checks/runs.py` - format_deployment_plan, create_check_run, find_open_prs
- `backend/src/ferry_backend/webhook/handler.py` - Extended with full Phase 2 pipeline replacing Phase 1 stub
- `tests/test_backend/test_dispatch_trigger.py` - 8 tests for dispatch triggering
- `tests/test_backend/test_check_runs.py` - 10 tests for Check Run creation and PR lookup
- `tests/test_backend/test_handler_phase2.py` - 7 integration tests for handler Phase 2 flow
- `tests/test_backend/test_handler.py` - Updated Phase 1 handler tests for Phase 2 compatibility

## Decisions Made
- GitHubClient instantiated at module level for Lambda cold start optimization; auth methods called per-invocation for fresh credentials
- Merge-base comparison (default_branch...head) for PR branches gives complete diff; before...after for default branch shows just the merge commit changes
- find_open_prs used for both PR identification on feature branches and merged-PR number lookup on default branch pushes
- Config diff only triggered when "ferry.yaml" is in the changed_files list (not on every push)
- Payload size check at 65535 bytes with skip-and-log-error behavior (not silent truncation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated Phase 1 handler tests for Phase 2 compatibility**
- **Found during:** Task 2 (Handler pipeline wiring)
- **Issue:** Phase 1 handler tests used `FERRY_PRIVATE_KEY="test-private-key"` which failed when handler now calls generate_app_jwt with real PEM key parsing. Also needed httpx mocks for GitHub API endpoints and moto AWS credentials.
- **Fix:** Added autouse `_mock_jwt` fixture to monkeypatch generate_app_jwt, added `_mock_phase2_apis` helper for minimal API endpoint mocks, added fake AWS credentials for moto, updated test assertions from "accepted" to "processed" status.
- **Files modified:** tests/test_backend/test_handler.py
- **Verification:** All 7 Phase 1 handler tests pass
- **Committed in:** 29f3c31 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary fix for existing tests that broke due to handler implementation change. No scope creep.

## Issues Encountered
None beyond the Phase 1 test compatibility fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (App Core Logic) is now complete: config loading, change detection, dispatch triggering, and Check Run creation all wired into the handler
- Phase 3 (Build + Lambda Deploy) can proceed -- it consumes the DispatchPayload sent by trigger_dispatches
- The composite action will receive the serialized JSON payload as a workflow_dispatch input

## Self-Check: PASSED

All 9 files verified on disk. Both task commits (d7e2e0c, 29f3c31) verified in git log.

---
*Phase: 02-app-core-logic*
*Completed: 2026-02-24*
