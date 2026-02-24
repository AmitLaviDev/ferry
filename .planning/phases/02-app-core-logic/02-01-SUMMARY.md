---
phase: 02-app-core-logic
plan: 01
subsystem: api
tags: [pydantic, yaml, github-api, config, base64]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: GitHubClient (client.py), ConfigError (errors.py), frozen model conventions
provides:
  - fetch_ferry_config function (GitHub Contents API fetch at commit SHA)
  - parse_config function (YAML string to dict with error handling)
  - FerryConfig, LambdaConfig, StepFunctionConfig, ApiGatewayConfig Pydantic models
  - validate_config function (dict to typed FerryConfig with fail-fast semantics)
affects: [02-02-change-detection, 02-03-dispatch-orchestration]

# Tech tracking
tech-stack:
  added: [pyyaml]
  patterns: [model_validator for computed defaults on frozen models, Contents API base64 decoding]

key-files:
  created:
    - backend/src/ferry_backend/config/__init__.py
    - backend/src/ferry_backend/config/loader.py
    - backend/src/ferry_backend/config/schema.py
    - tests/test_backend/test_config_loader.py
    - tests/test_backend/test_config_schema.py
  modified: []

key-decisions:
  - "object.__setattr__ for frozen model validator default (function_name defaults to name)"
  - "ConfigError wraps both HTTP errors and ValidationError for uniform fail-fast behavior"

patterns-established:
  - "Contents API fetch: client.get with ref=sha param, base64-decode response content field"
  - "Schema validation: model_validate wrapped in try/except, re-raise as ConfigError"
  - "All config models frozen with extra=forbid, matching Phase 1 convention"

requirements-completed: [CONF-01, CONF-02]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 2 Plan 1: Config Loading & Schema Summary

**ferry.yaml fetch via GitHub Contents API with Pydantic v2 typed schema validation and fail-fast ConfigError semantics**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T15:36:46Z
- **Completed:** 2026-02-24T15:39:19Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Config loader fetches ferry.yaml at exact commit SHA via GitHub Contents API and base64-decodes it
- YAML parser handles valid, invalid, and empty input with appropriate ConfigError messages
- Pydantic v2 models for all three resource types with type-specific required/optional fields
- LambdaConfig defaults runtime to python3.10 and function_name to name via model_validator
- validate_config wraps Pydantic ValidationError in ConfigError for uniform error handling
- 19 tests total (6 loader + 13 schema) all passing with zero lint errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Config loader (fetch + parse)** - `5c8dd39` (test: RED) -> `c868491` (feat: GREEN)
2. **Task 2: Config schema (Pydantic models)** - `41f7a0e` (test: RED) -> `ccee018` (feat: GREEN)

_TDD tasks have two commits each (test -> feat)_

## Files Created/Modified
- `backend/src/ferry_backend/config/__init__.py` - Package init for config module
- `backend/src/ferry_backend/config/loader.py` - fetch_ferry_config and parse_config functions
- `backend/src/ferry_backend/config/schema.py` - FerryConfig, LambdaConfig, StepFunctionConfig, ApiGatewayConfig models + validate_config
- `tests/test_backend/test_config_loader.py` - 6 tests for fetch (200/404/500) and parse (valid/invalid/empty)
- `tests/test_backend/test_config_schema.py` - 13 tests for all models and validate_config wrapper

## Decisions Made
- Used `object.__setattr__` for frozen model validator to set function_name default to name (Pydantic frozen models prevent normal attribute assignment)
- ConfigError wraps both HTTP errors (from fetch) and ValidationError (from schema validation) providing a uniform fail-fast error type for the caller
- Tests use pytest-httpx for mocking GitHubClient HTTP responses, consistent with Phase 1 test patterns

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Config loading and schema validation complete, ready for Plan 02 (change detection)
- fetch_ferry_config + parse_config + validate_config form the config pipeline that change detection will consume
- FerryConfig model provides typed access to all resource sections for dispatch matching

## Self-Check: PASSED

All 5 created files verified on disk. All 4 task commits (5c8dd39, c868491, 41f7a0e, ccee018) verified in git log.

---
*Phase: 02-app-core-logic*
*Completed: 2026-02-24*
