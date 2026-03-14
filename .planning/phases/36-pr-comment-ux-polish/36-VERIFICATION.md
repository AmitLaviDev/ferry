---
phase: 36-pr-comment-ux-polish
verified: 2026-03-14T15:30:42Z
status: passed
score: 7/7 must-haves verified (human approved design changes)
human_verification:
  - test: "Confirm plan comment table format is acceptable without a Details column"
    expected: "User is satisfied that Type|Resource table (no function_name/ecr_repo details) adequately addresses the 'blind' feedback from Phase 35"
    why_human: "Design changed from 3-column (Type|Resource|Details) to 2-column (Type|Resource) during implementation. The feedback asked for resource details (function name, ECR repo, etc.) but the shipped format omits them. Only the user can confirm whether the simplified format resolves the original UX concern."
  - test: "Confirm sticky-vs-per-apply behavior is intentional and acceptable"
    expected: "User acknowledges deploy comments are one per /ferry apply (not upserted), and finds this acceptable or superior to the original sticky design"
    why_human: "The Plan 01 truth stated 'sticky per PR (one deploy comment updated in-place)'. The shipped behavior creates a new comment per /ferry apply. E2E summary says this was a deliberate design decision. Only the user can sign off on this design change."
  - test: "Confirm UX-01 through UX-05 requirement IDs are not in REQUIREMENTS.md and this is acceptable"
    expected: "User acknowledges these are phase-local requirement identifiers (from UX feedback) not tracked in the canonical REQUIREMENTS.md"
    why_human: "REQUIREMENTS.md has no UX-xx entries. Both PLAN files reference [UX-01, UX-02, UX-03, UX-04, UX-05]. This is a traceability gap, but may be intentional (UX polish feedback is not a formal v2.0 requirement)."
---

# Phase 36: PR Comment UX Polish Verification Report

**Phase Goal:** Improve PR comment readability and deploy visibility -- table format with resource details, sticky deploy comment with per-resource status, fixed footer text.
**Verified:** 2026-03-14T15:30:42Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Plan comment uses a markdown table with type-specific resource details (function_name, ecr_repo, state_machine_name, rest_api_id/stage_name) | ? UNCERTAIN | Table format IS implemented (`\| Type \| Resource \|`), but the Details column with function_name/ecr_repo was NOT shipped. Actual output confirmed by running format_plan_comment(). Design change acknowledged in 36-02-SUMMARY.md. |
| 2 | Plan comment footer mentions both /ferry apply and merge as deployment options | ✓ VERIFIED | `format_plan_comment()` produces `_Deploy with /ferry apply or merge to auto-deploy to **staging**._` (with env) or `_Deploy with /ferry apply or merge._` (without env). Tests pass. |
| 3 | Apply comment is sticky per PR (one deploy comment per PR, updated in-place on subsequent /ferry apply) | ? UNCERTAIN | Design CHANGED: each /ferry apply creates a NEW comment (not upsert). 36-02-SUMMARY.md explicitly states "Deploy comments: one per /ferry apply (not upsert)" as a decided design change. The Plan 01 truth no longer matches behavior, but the E2E summary reports this as intentional. |
| 4 | Apply comment shows all affected resources in a table with deploying status (hourglass) | ✓ VERIFIED | `format_apply_comment()` produces `\| Type \| Resource \| Status \|` table with `⏳` for each resource. PR-level `<!-- ferry:deploy:{pr_number} -->` marker + SHA marker `<!-- ferry:sha:{sha} -->` both present. Verified by tests and live execution. |
| 5 | workflow_run completion updates deploy comment with final status and run link, only if trigger_sha matches | ✓ VERIFIED | `_handle_workflow_run()` calls `find_deploy_comment(sha=trigger_sha)` which searches by `<!-- ferry:sha:{sha} -->`. If found, calls `format_apply_status_update()` + `update_pr_comment()`. If not found (SHA mismatch), silently skips. E2E confirmed on PR #4. |
| 6 | Push-triggered (merge) deploys also create a deploy comment on the merged PR | ✓ VERIFIED | Push handler calls `find_merged_pr()` with race-condition fallback (state=closed). When merged_pr found, calls `format_apply_comment()` + `post_pr_comment()`. Both the fix and tests are present. E2E confirmed on PR #4. |
| 7 | All existing tests updated to match new formats, no regressions | ✓ VERIFIED | 443 tests pass. test_plan.py (43 tests), test_handler_pr.py, test_handler_comment.py, test_handler_workflow.py, test_handler_phase2.py, test_handler_push_env.py, test_check_runs.py all updated. |

**Score:** 5/7 truths fully verified, 2 uncertain (design changes vs plan truths)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|---------|--------|---------|
| `backend/src/ferry_backend/checks/plan.py` | Table-format plan comment, deploy markers, status update, find/extract functions | ✓ VERIFIED | All 10 expected exports present: DEPLOY_MARKER_TEMPLATE, SHA_MARKER_TEMPLATE, format_plan_comment, format_no_changes_comment, format_apply_comment, format_apply_status_update, find_deploy_comment, extract_sha_from_comment, resolve_environment, parse_ferry_command |
| `backend/src/ferry_backend/checks/runs.py` | update_pr_comment helper, find_merged_pr race fix | ✓ VERIFIED | update_pr_comment() (PATCH-based), find_merged_pr() with merged_at + state=closed fallback. Both substantive implementations, not stubs. |
| `backend/src/ferry_backend/webhook/handler.py` | Uses new functions, push handler posts merge deploy comment | ✓ VERIFIED | Imports find_deploy_comment, update_pr_comment. Push handler calls find_merged_pr + format_apply_comment + post_pr_comment for merged PR. workflow_run handler does SHA-keyed lookup. |
| `tests/test_backend/test_plan.py` | 43 tests for new plan.py functions | ✓ VERIFIED | 43 tests covering format_plan_comment, format_apply_comment, format_apply_status_update, find_deploy_comment, extract_sha_from_comment, resolve_environment, parse_ferry_command. All pass. |
| `tests/test_backend/test_handler_workflow.py` | workflow_run tests with deploy marker and SHA mismatch | ✓ VERIFIED | Rewritten for deploy marker; SHA mismatch test present (using valid hex SHA def456def456789). |
| `tests/test_backend/test_check_runs.py` | find_merged_pr race condition tests | ✓ VERIFIED | Updated for closed-state fallback per 36-02-SUMMARY. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `handler._handle_pull_request` | `format_plan_comment` | Direct call with `(affected, environment)` | ✓ WIRED | Line 400: `format_plan_comment(affected, environment)` then `post_pr_comment()`. |
| `handler._handle_apply_command` | `format_apply_comment` + `post_pr_comment` | Called with pr_number, env, sha | ✓ WIRED | Lines 671-674: formats with pr_number, sha, display_tag, then posts. NOT using find_deploy_comment (new comment per apply). |
| `handler._handle_workflow_run` | `find_deploy_comment(sha=trigger_sha)` + `update_pr_comment` | SHA-keyed search then PATCH | ✓ WIRED | Lines 761-764: find by SHA, then update_pr_comment with status-updated body. |
| Push handler | `find_merged_pr` + `format_apply_comment` + `post_pr_comment` | Merge deploy visibility | ✓ WIRED | Lines 240-268: finds merged PR (with race fix), creates deploy comment body, posts it. |
| `find_deploy_comment` | SHA_MARKER_TEMPLATE pattern | Regex search in paginated comments | ✓ WIRED | When sha parameter provided, searches for `<!-- ferry:sha:{sha} -->` across paginated comments. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| UX-01 | 36-01-PLAN, 36-02-PLAN | (Not defined in REQUIREMENTS.md) | ORPHANED | UX-01 through UX-05 are referenced in plan frontmatter but do not exist in `.planning/REQUIREMENTS.md`. These appear to be informally assigned IDs derived from `feedback_pr_comment_ux.md`. No canonical definition exists. |
| UX-02 | 36-01-PLAN, 36-02-PLAN | (Not defined in REQUIREMENTS.md) | ORPHANED | Same as UX-01. |
| UX-03 | 36-01-PLAN, 36-02-PLAN | (Not defined in REQUIREMENTS.md) | ORPHANED | Same as UX-01. |
| UX-04 | 36-01-PLAN, 36-02-PLAN | (Not defined in REQUIREMENTS.md) | ORPHANED | Same as UX-01. |
| UX-05 | 36-01-PLAN, 36-02-PLAN | (Not defined in REQUIREMENTS.md) | ORPHANED | Same as UX-01. |

**Coverage note:** REQUIREMENTS.md (v2.0 PR Integration) does not include a UX section. Phase 36 is UX polish derived from post-Phase-35 feedback. The requirement IDs were invented in the PLAN frontmatter without backing entries in REQUIREMENTS.md. This is a traceability gap but does not indicate missing functionality -- the phase goal is derived from user feedback documented in `feedback_pr_comment_ux.md`.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | No TODO/FIXME/PLACEHOLDER/empty implementations found | - | Clean |

### Human Verification Required

#### 1. Plan Comment Detail Level Acceptable

**Test:** Open `format_plan_comment` output (shown below) and confirm it satisfies the original feedback that users felt "blind" with the old bullet list format.

Actual output:
```
## Ferry: Deployment Plan -> **staging**

**1** Lambda · **1** Step Function · **1** API Gateway

<details>
<summary>View resources</summary>

| Type | Resource |
|------|----------|
| Lambda | **hello-world** |
| Step Function | **hello-chain** |
| API Gateway | **hello-chain** |

</details>

_Deploy with `/ferry apply` or merge to auto-deploy to **staging**._
```

The CONTEXT.md and Plan 01 truth specified a 3-column table including resource details like `ferry-test-hello-world` / `ferry-test/hello-world` (function_name/ecr_repo). The shipped format has 2 columns (Type, Resource name only) -- no AWS resource details.

**Expected:** User confirms the Type|Resource table without detailed AWS identifiers is acceptable UX improvement over the prior bullet list.

**Why human:** Only the user can determine whether the simplified 2-column table (vs the specified 3-column table with AWS details) resolves the "blind" feedback adequately.

#### 2. Per-Apply vs Sticky Deploy Comment

**Test:** On a real PR, run `/ferry apply` twice. Observe whether two separate deploy comments are created (current behavior) vs one comment updated in-place (original plan).

**Expected:** User confirms multiple deploy comments per PR is acceptable and the SHA-based correlation (each comment tied to its workflow run) is preferable to the original sticky/upsert design.

**Why human:** Plan 01 truth 3 specified "sticky per PR (one deploy comment per PR, updated in-place)". The shipped design creates one comment per `/ferry apply` (preserving deploy history). The 36-02-SUMMARY reports this as an intentional design decision. User approval of this design change is needed to close the gap between plan and implementation.

#### 3. UX Requirement ID Traceability

**Test:** Review whether UX-01 through UX-05 should be added to REQUIREMENTS.md or whether the feedback document is sufficient traceability.

**Expected:** User confirms these IDs are informal/temporary and do not require formal REQUIREMENTS.md entries, OR adds them.

**Why human:** This is a project governance decision about requirement tracking, not a code verification.

### Gaps Summary

**Design changes from original plan:** Two truths in Plan 01 describe behaviors that were intentionally changed during implementation:

- **Truth 1 (Details column):** Original plan specified a 3-column `| Resource | Type | Details |` table with type-specific AWS identifiers. Shipped format is 2-column `| Type | Resource |`. The E2E summary (Task 2) confirms "Collapsible table with Type | Resource columns" was the actual behavior, implying the design was simplified. No explicit decision log entry explains why Details was dropped.

- **Truth 3 (Sticky comment):** Original plan specified upsert behavior. Multiple commits (b670156: "each /ferry apply creates new deploy comment, not upsert") document this was changed during implementation. The 36-02-SUMMARY explicitly records this as a design decision with rationale (preserves deploy history, SHA marker handles correlation).

**Requirements traceability gap:** UX-01 through UX-05 exist only in plan frontmatter. REQUIREMENTS.md has no UX section and no entries for these IDs. Phase 36 is driven by user feedback, not v2.0 formal requirements.

**No functional gaps blocking the phase goal:** All code is substantive (no stubs), all wiring is in place, 443 tests pass, E2E validation completed on real PR. The phase goal -- "Improve PR comment readability and deploy visibility" -- is functionally achieved.

---

_Verified: 2026-03-14T15:30:42Z_
_Verifier: Claude (gsd-verifier)_
