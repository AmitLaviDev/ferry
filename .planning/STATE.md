# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v1.2 End-to-End Validation -- Phase 17: End-to-End Loop Validation

## Current Position

Phase: 17 of 17 (End-to-End Loop Validation)
Plan: 17-02 in progress (Task 2: E2E push-to-deploy loop)
Status: Executing -- iterative bug fix cycle
Last activity: 2026-03-07 -- Fixed 7 bugs during E2E loop, re-running GHA

Progress: [########░░] 80% (v1.2)

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:**
| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 11 | 01 | 1min | 2 | 10 |
| 11 | 02 | 1min | 1 | 1 |
| 12 | 01 | 3min | 2 | 11 |
| 12.1 | 01 | 2min | 2 | 6 |
| 13 | 01 | 2min | 2 | 6 |
| 14 | 01 | 3min | 2 | 4 |
| 14 | 02 | 1min | 1 | 1 |
| 14 | 03 | 2min | 1 | 1 |

**v1.2:**
| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 16 | 01 | 2min | 2 | 6 |
| 16 | 02 | 1min | 2 | 5 |
| 17 | 01 | 1min | 2 | 2 |

## Accumulated Context

### Decisions

All v1.0 and v1.1 decisions logged in PROJECT.md Key Decisions table and STATE.md history.

**v1.2:**
- External composite action syntax: `{owner}/{repo}/{path}@{ref}` (not `path:` input)
- Test repo runtime: python3.12 (latest stable Lambda runtime)
- Lambda deploy IAM policy needs 7 actions: UpdateFunctionCode, GetFunction, GetFunctionConfiguration, PublishVersion, UpdateAlias, CreateAlias, GetAlias
- Combined TF tasks when tflint enforces unused declarations rule
- Guard on any non-200 (not just 403) for PR lookup functions -- covers rate limits and server errors too
- Ferry repo made public (required for cross-repo composite action references)
- Lambda execution role needs ecr:BatchGetImage + ecr:GetDownloadUrlForLayer for container image Lambdas

### Bugs Fixed in 17-02 (E2E iteration)

| # | Bug | Root Cause | Fix Commit |
|---|-----|-----------|------------|
| 1 | ferry repo private → action not found | GHA can't ref actions from private repos | Made repo public |
| 2 | PEP 668 externally managed Python | Ubuntu GHA runner rejects `uv pip install --system` | Added setup-python@v5 to all actions |
| 3 | Python 3.12 vs requires-python>=3.14 | setup-python used 3.12, package needs 3.14 | Changed to python-version: "3.14" |
| 4 | `${{ github.token }}` in input descriptions | GHA rejects template expressions in description fields | Removed expressions from descriptions |
| 5 | Dockerfile path resolves to Python stdlib | `__file__` in site-packages != action directory | Bundled Dockerfile in package, use importlib.resources |
| 6 | `TypeError: bytes-like object` in ECR login | docker login missing text=True for str input | Added text=True to subprocess.run |
| 7 | Waiter needs GetFunctionConfiguration | function_updated waiter polls with GetFunctionConfiguration | Added permission to deploy IAM policy |
| 8 | Lambda can't access ECR image | Lambda execution role needs ecr:BatchGetImage + GetDownloadUrlForLayer + GetAuthorizationToken | Added ECR pull + auth to execution role |

### Pending Todos

- Remove debug logging from deploy.py (raw error output) after E2E passes
- Verify self-deploy IAM policy also has GetFunctionConfiguration (shared/data.tf)

### Blockers/Concerns

- Python 3.14 arm64 Lambda base image availability on public.ecr.aws must be verified (fallback: Python 3.13 or custom base)

## Session Continuity

Last session: 2026-03-07
Stopped at: 17-02 Task 2 (E2E push-to-deploy loop) -- waiting for GHA run 22805136282 after fixing 8 bugs
Resume: Re-run 22805136282 is in progress. Check result with `gh run view 22805136282 -R AmitLaviDev/ferry-test-app`
Next steps on success:
  1. Verify Lambda LastModified updated
  2. Invoke Lambda with --qualifier live, confirm v2 greeting
  3. Create 17-02-SUMMARY.md
  4. Proceed to 17-03 (repeatability proof + validation report)
Next steps on failure:
  1. Check logs: `gh run view 22805136282 -R AmitLaviDev/ferry-test-app --log-failed`
  2. Fix bug, push, re-run
