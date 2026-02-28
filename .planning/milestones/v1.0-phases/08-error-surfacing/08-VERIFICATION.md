---
phase: 08-error-surfacing
verified: 2026-02-28T08:00:00Z
status: passed
score: 13/13 must-haves verified
---

# Phase 8: Error Surfacing Verification Report

**Phase Goal:** Build and deploy failures are clearly surfaced to developers in PR status checks and GHA workflow logs — no silent failures, no need to check CloudWatch
**Verified:** 2026-02-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Auth failures produce a structured error response and log — not an unstructured Lambda 500 | VERIFIED | `handler.py` lines 243-247: `except GitHubAuthError as exc:` returns `_response(500, {"status": "auth_error"})` with `log.error(..., exc_info=True)` |
| 2 | Invalid ferry.yaml (default branch, post-merge) produces a PR comment — not a silent HTTP 200 | VERIFIED | `handler.py` lines 228-238: `find_merged_pr` is called; if found, `post_pr_comment` is called; if not, `log.warning` is emitted. Response is 200 with `status: config_error` (not silent) |
| 3 | Invalid ferry.yaml (PR branch) produces a PR comment — not a Check Run | VERIFIED | `handler.py` lines 222-226: `find_open_prs` → `post_pr_comment`. Test `test_config_error_posts_pr_comment_not_check_run` asserts zero Check Run calls |
| 4 | Build failure surfaces as a failed GitHub Check Run on the PR | VERIFIED | `build.py` lines 196, 216, 238: `report_check_run(..., "failure", ...)` called before `sys.exit(1)` or `raise` in all failure paths |
| 5 | Build failure surfaces as a clear error message in GHA workflow log | VERIFIED | `build.py` lines 195, 215, 237: `gha.error(format_error_detail(exc, hint))` emits `::error::` annotation with actionable hints |
| 6 | Deploy failure surfaces as a failed Check Run on the PR | VERIFIED | `deploy.py` lines 244, 250: `report_check_run(..., "failure", ...)` called before `sys.exit(1)` in all ClientError/WaiterError paths |
| 7 | Deploy failure surfaces as a clear error message in GHA workflow log | VERIFIED | `deploy.py` lines 243, 249: `gha.error(format_error_detail(exc, ...))` emits `::error::` annotation. Same pattern in `deploy_stepfunctions.py:214` and `deploy_apigw.py:271` |
| 8 | Unhandled exception cannot escape as raw Lambda 500 | VERIFIED | `handler.py` lines 249-253: `except Exception as exc:` catch-all returns `{"status": "internal_error", "error": "internal server error"}` without leaking details |
| 9 | Auth errors are NOT surfaced to developers via PR comment or Check Run | VERIFIED | `handler.py` auth handler only calls `log.error` and returns 500 — no `post_pr_comment`, no `create_check_run` |
| 10 | Successful build/deploy creates a success Check Run per resource | VERIFIED | `build.py` lines 246-249, `deploy.py` lines 212-215: `report_check_run(..., "success", ...)` called after success output |
| 11 | Skip events produce success Check Runs with explicit skip message | VERIFIED | `deploy.py` lines 190-193, `deploy_stepfunctions.py` lines 157-160, `deploy_apigw.py` lines 216-219: all call `report_check_run(..., "success", "Skipped ... (... unchanged)")` |
| 12 | AWS account IDs in error messages are partially masked | VERIFIED | `gha.py` lines 79-90: `mask_account_id()` masks to `****{last4}`. `build.py` uses `gha.mask_value(account_id)` for full masking in logs |
| 13 | Stack traces hidden by default but shown when FERRY_DEBUG=1 | VERIFIED | `report.py` lines 93-96: `format_error_detail` checks `FERRY_DEBUG` env var; returns only hint by default, appends traceback when `FERRY_DEBUG in ("1", "true", "yes")` |

**Score:** 13/13 truths verified

---

### Required Artifacts (Plan 01)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/ferry_backend/webhook/handler.py` | Top-level exception handler for auth, config, unhandled errors | VERIFIED | Lines 124-253: try block wraps steps 8-13; three except clauses (ConfigError, GitHubAuthError, Exception) all return structured JSON |
| `backend/src/ferry_backend/checks/runs.py` | `post_pr_comment` and `find_merged_pr` functions | VERIFIED | Lines 161-185 (`find_merged_pr`) and 188-216 (`post_pr_comment`) — substantive implementations, not stubs |
| `backend/src/ferry_backend/github/client.py` | `GitHubClient.patch()` method | VERIFIED | Lines 81-92: `patch()` method matches `get()`/`post()` pattern exactly |
| `utils/src/ferry_utils/errors.py` | `BuildError` and `DeployError` types | VERIFIED | Lines 24-29: both defined as `FerryError` subclasses with docstrings |

### Required Artifacts (Plan 02)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `action/src/ferry_action/report.py` | `report_check_run` and `format_error_detail` | VERIFIED | Lines 21-96: both functions present, substantive, non-stub |
| `action/src/ferry_action/gha.py` | `mask_account_id` helper | VERIFIED | Lines 79-90: function present and correct |
| `action/src/ferry_action/build.py` | `report_check_run` calls on success and failure | VERIFIED | Called at lines 196 (FileNotFoundError), 216 (build CalledProcessError), 238 (push CalledProcessError), 246-249 (success) |
| `action/src/ferry_action/deploy.py` | `report_check_run` calls on success, skip, failure | VERIFIED | Called at lines 190-193 (skip), 212-215 (success), 244 (ClientError), 250 (WaiterError) |
| `tests/test_action/test_report.py` | Tests for reporter and error formatting | VERIFIED | 160 lines; 5 `TestReportCheckRun` tests + 5 `TestFormatErrorDetail` tests — all substantive |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `handler.py` | `checks/runs.py` | `post_pr_comment` call on ConfigError | WIRED | Lines 224-226 and 231-233 call `post_pr_comment(github_client, repo, ...)` |
| `handler.py` | `ferry_utils/errors.py` | `except GitHubAuthError` import | WIRED | Line 41: `from ferry_utils.errors import ConfigError, GitHubAuthError`; line 243: `except GitHubAuthError as exc:` |
| `build.py` | `report.py` | `from ferry_action.report import` | WIRED | Line 22: `from ferry_action.report import format_error_detail, report_check_run` — used in 4 call sites |
| `deploy.py` | `report.py` | `from ferry_action.report import` | WIRED | Line 22: `from ferry_action.report import format_error_detail, report_check_run` — used in 4 call sites |
| `report.py` | GitHub Check Runs API | `httpx.post` | WIRED | Line 74: `httpx.post(url, headers=headers, json=body, timeout=_GITHUB_API_TIMEOUT)` with correct URL pattern |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WHOOK-03 | 08-01-PLAN, 08-02-PLAN | Build and deploy failures are surfaced in GitHub PR status checks and GHA workflow logs | SATISFIED | Backend: `handler.py` structured error responses; config errors as PR comments via `post_pr_comment`. Action: `report.py` posts per-resource Check Runs; `gha.error()` emits `::error::` annotations; `format_error_detail` with FERRY_DEBUG toggle. All four build/deploy modules report Check Runs on success and failure |

**REQUIREMENTS.md entry:** `- [x] **WHOOK-03**: Build and deploy failures are surfaced in GitHub PR status checks and GHA workflow logs` — marked complete.

No orphaned requirements. Both plans claim WHOOK-03 jointly; the combined implementation satisfies it.

---

### Action.yml github-token Input Coverage

| File | `github-token` input | `GITHUB_TOKEN` env | Status |
|------|---------------------|---------------------|--------|
| `action/build/action.yml` | Present (line 31-34) | Line 71: `GITHUB_TOKEN: ${{ inputs.github-token }}` | VERIFIED |
| `action/deploy/action.yml` | Present (lines 32-35) | Line 70: `GITHUB_TOKEN: ${{ inputs.github-token }}` | VERIFIED |
| `action/deploy-stepfunctions/action.yml` | Present (lines 31-34) | Line 69: `GITHUB_TOKEN: ${{ inputs.github-token }}` | VERIFIED |
| `action/deploy-apigw/action.yml` | Present (lines 33-36) | Line 73: `GITHUB_TOKEN: ${{ inputs.github-token }}` | VERIFIED |

---

### Anti-Patterns Found

None. Grep scan of all 10 modified/created files found zero instances of:
- `TODO`, `FIXME`, `XXX`, `HACK`, `PLACEHOLDER`
- `return null`, `return {}`, `return []`
- Stub implementations

---

### Test Results

```
272 passed in 3.42s
```

Phase 08 specific tests: 51 passed in 0.61s
- `tests/test_backend/test_handler_phase2.py` — 8 handler integration tests
- `tests/test_backend/test_check_runs.py` — 11 unit tests (find_merged_pr, post_pr_comment, create_check_run, format_deployment_plan)
- `tests/test_action/test_report.py` — 10 unit tests (report_check_run, format_error_detail)
- `tests/test_action/test_gha.py` — includes 5 mask_account_id tests

---

### Human Verification Required

None — all success criteria are mechanically verifiable. The Check Run API calls, GHA annotation emission, and error response structure are all covered by tests and confirmed by code inspection.

However, the following behaviors are inherently verified only in a live GHA environment:

1. **Check Run rendering in PR UI**
   - What to verify: Push a branch with a deliberate build failure; confirm a failed "Ferry: {name} build" Check Run appears in the PR status bar
   - Why human: Requires live GHA runner with real GitHub token and ECR credentials

2. **GHA workflow log annotations**
   - What to verify: Failed deploy should show `::error::` annotation highlighted in the Actions UI log viewer
   - Why human: GHA annotation rendering requires a real Actions environment

These are integration concerns only. All underlying mechanics are verified by automated tests.

---

## Summary

Phase 8 fully achieves its goal. The codebase now guarantees:

**Backend (08-01):** No exception can escape the handler as an unstructured Lambda 500. Three exception tiers are in place: `ConfigError` → PR comment (not Check Run), `GitHubAuthError` → structured 500 with structured logging, `Exception` → generic 500 without leaking internal details. The `post_pr_comment` / `find_merged_pr` functions correctly handle both PR-branch and default-branch config errors.

**Action (08-02):** Every build/deploy module reports per-resource GitHub Check Runs on success, skip, and failure. The `report.py` module is non-critical (wrapped in try/except, gracefully no-ops without `GITHUB_TOKEN`). GHA `::error::` annotations with actionable hints are emitted in all failure paths. `FERRY_DEBUG` toggle controls whether stack traces appear. All four composite action.yml files pass `GITHUB_TOKEN` to Python.

WHOOK-03 is fully closed. Developers will see failed Check Runs in PR status and actionable error messages in GHA workflow logs for any build or deploy failure.

---

_Verified: 2026-02-28_
_Verifier: Claude (gsd-verifier)_
