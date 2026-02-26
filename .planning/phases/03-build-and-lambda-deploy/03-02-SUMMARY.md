---
phase: 03-build-and-lambda-deploy
plan: 02
subsystem: action
tags: [dockerfile, docker-build, ecr, magic-dockerfile, container-image, build-secrets]

requires:
  - phase: 03-build-and-lambda-deploy
    provides: "Composite action scaffold (action.yml, gha.py helpers) from plan 01"
  - phase: 01-foundation
    provides: "DispatchPayload and LambdaResource Pydantic models in ferry-utils"
provides:
  - "Magic Dockerfile for building any Lambda from main.py + requirements.txt"
  - "build.py: Docker build command construction, ECR login, image push, digest capture"
  - "Configurable Python runtime version via ARG PYTHON_VERSION build arg"
  - "Private GitHub repo dependency support via Docker build secrets"
affects: [03-build-and-lambda-deploy]

tech-stack:
  added: [docker-buildkit-secrets, ecr-get-login-password, docker-inspect-repo-digests]
  patterns: [magic-dockerfile-glob-trick, subprocess-command-list-construction, ecr-login-pipe-pattern]

key-files:
  created:
    - action/Dockerfile
    - action/src/ferry_action/build.py
    - tests/test_action/test_build.py
  modified: []

key-decisions:
  - "Dockerfile path resolved relative to build.py module (Path(__file__).parent.parent.parent / Dockerfile)"
  - "ECR registry domain extracted from URI by splitting on first slash for docker login"
  - "Error handling with common failure hints: missing docker, bad requirements, ECR auth"

patterns-established:
  - "Magic Dockerfile pattern: ARG PYTHON_VERSION + glob trick for optional files + build secret mount"
  - "Subprocess command construction: build list[str] for subprocess.run, testable without docker"
  - "ECR login pipe: aws ecr get-login-password | docker login --password-stdin"

requirements-completed: [BUILD-01, BUILD-02, BUILD-03, BUILD-04, BUILD-05]

duration: 2min
completed: 2026-02-26
---

# Phase 3 Plan 02: Magic Dockerfile and Build Module Summary

**Magic Dockerfile with configurable Python runtime, optional system packages via glob trick, and private repo build secrets; build.py constructs Docker commands, authenticates to ECR, pushes images, and captures digests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T08:06:24Z
- **Completed:** 2026-02-26T08:09:10Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Magic Dockerfile that builds any Lambda from main.py + requirements.txt using configurable Python runtime (ARG PYTHON_VERSION)
- Glob trick (COPY system-requirements.tx[t]) handles optional system packages and config scripts without failing when absent
- Docker build secret support for private GitHub repo dependencies via --mount=type=secret,id=github_token
- Build module with testable pure functions: parse_runtime_version, build_ecr_uri, build_docker_command, ecr_login, push_image
- 13 TDD tests covering all build functions with mocked subprocess calls

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for build module** - `0608e01` (test)
2. **Task 1 (GREEN): Magic Dockerfile + build.py implementation** - `5c4252b` (feat)

_Note: TDD task with RED (failing tests) and GREEN (implementation) commits._

## Files Created/Modified
- `action/Dockerfile` - Magic Dockerfile with ARG PYTHON_VERSION, glob trick for optional files, build secret mount, main.handler CMD
- `action/src/ferry_action/build.py` - Docker build command construction, ECR login/push, digest capture, GHA output/summary writing
- `tests/test_action/test_build.py` - 13 tests: ECR URI, runtime parsing, docker command, ECR login, push/digest, main orchestrator, mask account ID

## Decisions Made
- Dockerfile path resolved relative to build.py module location (Path(__file__).resolve().parent.parent.parent / "Dockerfile") -- avoids reliance on working directory
- ECR registry domain extracted from full URI by splitting on first slash -- simpler than separate parameter
- Error handling wraps subprocess calls with common failure hints (missing docker, bad requirements.txt, ECR auth failure) per CONTEXT.md decisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Build module complete; Plan 03 (Lambda deploy) can now use the image-uri and image-digest outputs from the build step
- Dockerfile is referenced by action/build/action.yml which invokes python -m ferry_action.build
- GHA helpers (gha.py) from Plan 01 are fully integrated for outputs, groups, masks, and summaries

---
*Phase: 03-build-and-lambda-deploy*
*Completed: 2026-02-26*
