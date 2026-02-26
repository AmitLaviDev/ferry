---
phase: 03-build-and-lambda-deploy
plan: 01
subsystem: action
tags: [composite-action, gha, oidc, pydantic, matrix, ecr, lambda]

requires:
  - phase: 01-foundation
    provides: "DispatchPayload and LambdaResource Pydantic models in ferry-utils"
provides:
  - "Three composite action.yml files (setup, build, deploy) with correct inputs/outputs"
  - "parse_payload.py: DispatchPayload -> GHA matrix JSON transformer"
  - "gha.py: GHA workflow command helpers (outputs, groups, masks, summaries)"
  - "OIDC auth wired in build and deploy actions via aws-actions/configure-aws-credentials@v4"
affects: [03-build-and-lambda-deploy]

tech-stack:
  added: [boto3, aws-actions/configure-aws-credentials@v4, astral-sh/setup-uv@v4]
  patterns: [composite-action-with-python-scripts, env-var-input-passing, github-output-file]

key-files:
  created:
    - action/setup/action.yml
    - action/build/action.yml
    - action/deploy/action.yml
    - action/src/ferry_action/parse_payload.py
    - action/src/ferry_action/gha.py
    - tests/test_action/test_parse_payload.py
    - tests/test_action/test_gha.py
  modified:
    - action/pyproject.toml
    - .gitignore

key-decisions:
  - "Default runtime python3.12 in matrix (dispatch payload intentionally lean, runtime is a build concern)"
  - "Each composite action installs ferry-action via uv (matrix jobs run in separate runners)"
  - "gha.py uses file-based outputs (GITHUB_OUTPUT) with stdout fallback for local testing"

patterns-established:
  - "Composite action pattern: action.yml -> uv install -> python -m ferry_action.module"
  - "Input passing: GHA inputs mapped to INPUT_* env vars for Python scripts"
  - "OIDC auth: aws-actions/configure-aws-credentials@v4 as first step in build/deploy"

requirements-completed: [ACT-01, AUTH-02]

duration: 3min
completed: 2026-02-26
---

# Phase 3 Plan 01: Composite Action Architecture Summary

**Three-action composite scaffold (setup/build/deploy) with DispatchPayload-to-matrix parser and GHA workflow command helpers**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T08:00:47Z
- **Completed:** 2026-02-26T08:04:02Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Three composite action.yml files with full inputs/outputs definitions for the setup/build/deploy fan-out architecture
- Payload parser that transforms DispatchPayload JSON into GHA matrix JSON with Lambda resource filtering
- GHA logging helpers for workflow commands (outputs, groups, masks, errors, warnings, summaries)
- OIDC authentication wired in build and deploy actions via aws-actions/configure-aws-credentials@v4
- 23 tests covering payload parsing, matrix generation, and all GHA helper functions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create three composite action.yml files + payload parser + GHA helpers** - `61b2078` (feat)
2. **Task 2: Tests for payload parser and GHA helpers** - `e941c2a` (test)

## Files Created/Modified
- `action/setup/action.yml` - Composite action: parse dispatch payload, output matrix JSON
- `action/build/action.yml` - Composite action: OIDC auth + Docker build + ECR push (placeholder script)
- `action/deploy/action.yml` - Composite action: OIDC auth + Lambda deploy (placeholder script)
- `action/src/ferry_action/parse_payload.py` - DispatchPayload -> GHA matrix JSON with Lambda filtering
- `action/src/ferry_action/gha.py` - GHA workflow command helpers (set_output, groups, masks, summaries)
- `action/pyproject.toml` - Added boto3 dependency for upcoming build/deploy scripts
- `.gitignore` - Added `!action/build/` exception (Python `build/` pattern was catching action subdir)
- `tests/test_action/__init__.py` - Test package init
- `tests/test_action/test_parse_payload.py` - 12 tests: valid/invalid payloads, filtering, matrix format
- `tests/test_action/test_gha.py` - 11 tests: all GHA helper functions with file and stdout outputs

## Decisions Made
- Default runtime "python3.12" in matrix output -- dispatch payload intentionally does not carry runtime (it's a build concern from ferry.yaml, not a dispatch concern). Build action accepts runtime as overridable input.
- Each composite action (setup, build, deploy) includes its own uv install step because matrix jobs run on separate GHA runners.
- gha.py set_output uses the file-based GITHUB_OUTPUT approach with a deprecated set-output fallback for local testing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed .gitignore blocking action/build/ directory**
- **Found during:** Task 1 (creating composite action files)
- **Issue:** Python standard `.gitignore` pattern `build/` was catching `action/build/action.yml`
- **Fix:** Added `!action/build/` exception to `.gitignore`
- **Files modified:** `.gitignore`
- **Verification:** `git check-ignore` confirms action/build/ is no longer ignored
- **Committed in:** `61b2078` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix to allow committing the build action file. No scope creep.

## Issues Encountered
None beyond the gitignore deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Action scaffold complete; Plans 02 (Magic Dockerfile + ECR push) and 03 (Lambda deploy) build directly on this foundation
- parse_payload.py is fully functional for the setup action
- build.py and deploy.py are referenced in action.yml but not yet implemented (Plan 02 and 03)
- GHA helpers ready for use by build and deploy scripts

---
*Phase: 03-build-and-lambda-deploy*
*Completed: 2026-02-26*
