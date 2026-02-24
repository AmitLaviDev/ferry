---
phase: 02-app-core-logic
plan: 02
subsystem: detect
tags: [github-compare-api, change-detection, source-dir-matching, config-diffing, dataclass, structlog]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: GitHubClient httpx wrapper for API calls
  - phase: 02-app-core-logic/plan-01
    provides: FerryConfig, LambdaConfig, StepFunctionConfig, ApiGatewayConfig Pydantic models
provides:
  - get_changed_files function for Compare API fetch with truncation warning
  - match_resources function for source_dir prefix matching
  - detect_config_changes function for ferry.yaml config diffing
  - merge_affected function for deduplicating affected resource lists
  - AffectedResource frozen dataclass for downstream consumers
affects: [02-app-core-logic/plan-03, 02-app-core-logic/dispatch, 02-app-core-logic/checks]

# Tech tracking
tech-stack:
  added: []
  patterns: [source_dir trailing-slash normalization for prefix matching, frozen dataclass for immutable domain objects, structlog warning for API truncation, model_dump comparison for config diffing]

key-files:
  created:
    - backend/src/ferry_backend/detect/__init__.py
    - backend/src/ferry_backend/detect/changes.py
    - tests/test_backend/test_changes.py
  modified: []

key-decisions:
  - "AffectedResource uses frozen dataclass (not Pydantic) with tuple[str, ...] for immutable changed_files"
  - "Trailing slash normalization on source_dir prevents partial-prefix false matches (services/order vs services/order-ext)"
  - "detect_config_changes uses model_dump() dict comparison for field-level diffing"
  - "TYPE_CHECKING import for FerryConfig and GitHubClient to avoid circular imports"

patterns-established:
  - "Source_dir prefix matching: always normalize to trailing slash before startswith comparison"
  - "Config diffing: name-keyed dict comparison per resource type section"
  - "Section type mapping: _SECTION_TYPE_MAP dict for iterating all resource types generically"

requirements-completed: [DETECT-01]

# Metrics
duration: 5min
completed: 2026-02-24
---

# Phase 02 Plan 02: Change Detection Summary

**Compare API fetch with 300-file truncation warning, source_dir prefix matching with trailing-slash normalization, and ferry.yaml config diffing via model_dump comparison**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-24T15:36:49Z
- **Completed:** 2026-02-24T15:41:56Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- get_changed_files fetches from Compare API and handles initial push (zero SHA) and 300-file truncation warning
- match_resources maps changed files to ferry.yaml resources by source_dir prefix with trailing-slash normalization to prevent partial-prefix false matches
- detect_config_changes diffs old vs new FerryConfig to identify new, modified, and removed resources
- merge_affected deduplicates resources from both source and config change detection
- 17 tests covering all behaviors with zero ruff lint errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Compare API fetch + source_dir prefix matching** - `fe90781` (feat)
2. **Task 2: ferry.yaml config diff detection** - `c53a4c7` (feat)

## Files Created/Modified
- `backend/src/ferry_backend/detect/__init__.py` - Empty package init for detect module
- `backend/src/ferry_backend/detect/changes.py` - Core change detection: get_changed_files, match_resources, detect_config_changes, merge_affected, AffectedResource
- `tests/test_backend/test_changes.py` - 17 tests covering Compare API fetch, source_dir matching, config diffing, merge dedup

## Decisions Made
- AffectedResource uses frozen dataclass (not Pydantic) with tuple[str, ...] for changed_files immutability -- lighter weight than Pydantic for a simple domain object
- Trailing slash normalization on source_dir prevents partial-prefix false matches (e.g., "services/order" must not match "services/order-ext/main.py")
- detect_config_changes uses model_dump() dict comparison for field-level diffing -- leverages Pydantic's serialization for reliable equality checking
- TYPE_CHECKING import for FerryConfig and GitHubClient avoids circular imports at runtime while keeping type annotations

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Change detection module complete and ready for handler integration (Plan 03)
- AffectedResource provides the data structure consumed by dispatch and checks modules
- get_changed_files + match_resources + detect_config_changes + merge_affected form the complete change detection pipeline

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 02-app-core-logic*
*Completed: 2026-02-24*
