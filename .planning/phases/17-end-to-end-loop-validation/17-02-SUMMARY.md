---
phase: 17-end-to-end-loop-validation
plan: 02
subsystem: e2e
tags: [e2e, deploy, ecr, iam, gha, composite-action]

# Dependency graph
requires:
  - phase: 17-01
    provides: "403 bug fix in PR lookup"
  - phase: 16
    provides: "Test environment (ECR, Lambda, OIDC role, test repo)"
provides:
  - "Proven end-to-end push-to-deploy loop"
  - "9 bugs found and fixed across IaC, action code, and workflow config"
affects: [17-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "importlib.resources for bundled non-code files in installed packages"
    - "setup-python@v5 required in composite actions for PEP 668 compatibility"
    - "ECR repo policy needs lambda.amazonaws.com service principal for container image Lambdas"

key-files:
  created: []
  modified:
    - action/setup/action.yml
    - action/build/action.yml
    - action/deploy/action.yml
    - action/src/ferry_action/build.py
    - action/src/ferry_action/deploy.py
    - iac/test-env/main.tf
    - iac/test-env/data.tf

key-decisions:
  - "Made ferry repo public -- GHA can't reference composite actions from private repos"
  - "Bundled Dockerfile via importlib.resources -- __file__ path unreliable in site-packages"
  - "Added setup-python@v5 to all composite actions -- PEP 668 blocks uv pip install --system"
  - "ECR repo policy needs repository_lambda_read_access_arns for Lambda service principal"
  - "Guard on raw AWS error message, not just exception type, for accurate error reporting"

patterns-established:
  - "Composite actions need setup-python + setup-uv before uv pip install"
  - "ECR repos used by Lambda functions must grant lambda.amazonaws.com via repository policy"
  - "Use importlib.resources (not __file__) for package-bundled data files"

requirements-completed: [E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07]

# Metrics
duration: 2 days (iterative bug fixing across sessions)
completed: 2026-03-08
---

# Phase 17 Plan 02: E2E Push-to-Deploy Loop

**Full end-to-end loop validated: push -> webhook -> detect -> dispatch -> build -> ECR push -> Lambda deploy -> invoke returns expected response**

## Performance

- **Duration:** ~2 days (iterative across 2026-03-07 to 2026-03-08)
- **Bugs found and fixed:** 9
- **Files modified:** 7+
- **GHA runs to success:** ~8

## Accomplishments

- Proved the complete Ferry pipeline works end-to-end with real infrastructure
- Lambda invocation returns `{"message": "hello from ferry-test-v4"}` via `live` alias
- Fixed 9 bugs discovered during E2E validation (see bug tracker below)

## Bug Tracker

| # | Bug | Root Cause | Fix |
|---|-----|-----------|-----|
| 1 | Ferry repo private, action not found | GHA can't ref actions from private repos | Made repo public |
| 2 | PEP 668 externally managed Python | Ubuntu runner rejects `uv pip install --system` | Added setup-python@v5 to all actions |
| 3 | Python 3.12 vs requires-python>=3.14 | setup-python defaulted to runner Python | Changed to python-version: "3.14" |
| 4 | Template expressions in descriptions | GHA rejects `${{ }}` in input description fields | Removed expressions from descriptions |
| 5 | Dockerfile path resolves to stdlib | `__file__` in site-packages != action directory | Bundled Dockerfile, use importlib.resources |
| 6 | `TypeError: bytes-like object` in ECR login | docker login missing text=True | Added text=True to subprocess.run |
| 7 | Waiter needs GetFunctionConfiguration | function_updated waiter polls with GetFunctionConfiguration | Added permission to deploy IAM policy |
| 8 | Lambda can't access ECR image | Execution role needs ECR pull + auth permissions | Added ECR pull + auth to execution role |
| 9 | ECR repo policy missing Lambda service principal | Lambda service needs `lambda.amazonaws.com` in repo policy | Added repository_lambda_read_access_arns to ECR module |

## Verified End-to-End Chain

| Stage | Status |
|-------|--------|
| Push to test repo | Triggers webhook |
| Ferry Lambda receives webhook | Validates signature, deduplicates |
| Change detection | Matches ferry.yaml path mappings |
| workflow_dispatch | Triggered on test repo |
| GHA setup job | Parses Ferry payload into matrix |
| Container build | Magic Dockerfile builds successfully |
| ECR push | Image pushed with deployment tag |
| Lambda deploy | UpdateFunctionCode + PublishVersion + UpdateAlias |
| Invocation via `live` alias | Returns expected response (200) |

## Deviations from Plan

- Plan expected 1-2 iterations; took ~8 GHA runs and 9 bug fixes
- Pre-flight health check (Task 1) was done manually by user across sessions
- Bug #9 (ECR repo policy) was not anticipated in any prior analysis

## Pending Todos (carried forward)

- Remove debug logging from deploy.py (raw error output)
- Verify self-deploy IAM policy also has GetFunctionConfiguration (shared/data.tf)
- Add `name: "Ferry: deploy ${{ matrix.name }}"` to workflow template docs
- Suppress Docker credential warning in build.py (cosmetic)
- Improve deploy.py error mapping (AccessDeniedException can mean target role lacks perms, not caller)

## Next Phase Readiness

- E2E loop proven -- 17-03 (repeatability proof + validation report) can proceed
- All blocking bugs resolved
- Infrastructure stable and verified

## Self-Check: PASSED

Lambda deployed and invoked successfully. Full pipeline verified.

---
*Phase: 17-end-to-end-loop-validation*
*Completed: 2026-03-08*
