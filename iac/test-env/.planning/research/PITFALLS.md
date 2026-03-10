# Domain Pitfalls

**Domain:** Consolidating multiple GHA workflow files into a single unified `ferry.yml` with conditional jobs per resource type
**Researched:** 2026-03-10

## Critical Pitfalls

Mistakes that cause broken dispatches, silent failures, or require rework.

### Pitfall 1: Concurrency Groups Cancel Legitimate Parallel Dispatches

**What goes wrong:** The backend sends up to 3 `workflow_dispatch` events to the same `ferry.yml` (one per resource type). If the workflow defines a workflow-level `concurrency` group using `github.workflow` or `github.ref`, the second dispatch cancels the first (or the first's pending state), and the third cancels the second. Only 1 of 3 resource types actually deploys.

**Why it happens:** GHA concurrency groups are keyed by string. Multiple dispatches to the same workflow file from the same commit share the same `github.workflow` and `github.ref` values. With `cancel-in-progress: true`, running dispatches get killed. With `cancel-in-progress: false`, any existing *pending* job in the same group still gets cancelled by the newest queued job -- only 1 running + 1 pending survive at most. This is documented GHA behavior, not a bug.

**Consequences:** Only one resource type deploys per push. Silent partial deployment with no error. The cancelled runs show as "Cancelled" in GHA UI but Ferry backend already returned 204 (success) for all dispatches.

**Prevention:**
- Do NOT use workflow-level concurrency groups on the unified workflow at all. Each dispatch is independent and must run in parallel.
- If concurrency control is needed, scope it to `resource_type` from the dispatch payload: `concurrency: group: ferry-${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type }}-${{ github.ref }}`. This gives each type its own concurrency lane.
- Alternatively, use job-level concurrency groups (scoped per job) instead of workflow-level.

**Detection:** After a push affecting multiple types, check GHA Actions tab -- if only 1 workflow run completes and others show "Cancelled", this is the cause. Test early with a push that touches all 3 resource types.

**Confidence:** HIGH -- documented GHA behavior, confirmed by multiple community reports (https://github.com/orgs/community/discussions/9252, https://github.com/orgs/community/discussions/53506).

**Phase:** Must be addressed in the workflow template design phase (phase 1). This is a design-time decision, not a bug to fix later.

---

### Pitfall 2: Skipped Job Cascades Kill Downstream Dependencies

**What goes wrong:** The unified workflow has a `setup` job, then conditional type-specific jobs (`deploy-lambdas`, `deploy-step-functions`, `deploy-api-gateways`), then possibly a `summary` or `report` job. When a dispatch is for lambdas only, the SF and APGW jobs skip. If the summary job uses `needs: [deploy-lambdas, deploy-step-functions, deploy-api-gateways]`, it also skips because `success()` returns false when *any* needed job was skipped.

**Why it happens:** GHA's default status check function `success()` returns false if any job in the `needs` list was skipped. This is counterintuitive -- skipped is not the same as failed, but GHA treats it that way for dependency resolution. A skipped job reports "Success" status to branch protection, but the `success()` function in `if` conditions evaluates to false when a needed job is skipped.

**Consequences:** Summary/reporting jobs never run. If you add a final "gate" job for status checks, it skips too. The whole dependency chain after conditional jobs breaks.

**Prevention:**
- Use `if: ${{ !failure() && !cancelled() }}` instead of the default `success()` on any job that depends on conditional jobs. The `!failure()` pattern allows the job to run if dependencies succeeded OR were skipped, but still prevents running if a dependency genuinely failed.
- Alternative: Use `if: ${{ always() }}` but this runs even after failures, which may not be desired.
- Best pattern for Ferry: Do not create downstream jobs that depend on all three type jobs. Keep the type-specific jobs as terminal (no downstream dependencies). If a summary is needed, each type job handles its own reporting.

**Detection:** The summary/gate job shows "Skipped" in GHA UI when you expected it to run. Test with a single-type dispatch and verify all expected jobs execute.

**Confidence:** HIGH -- well-documented GHA behavior (https://github.com/orgs/community/discussions/45058, https://github.com/actions/runner/issues/491).

**Phase:** Workflow template design phase. Decide the job dependency graph up front.

---

### Pitfall 3: Empty Matrix from fromJson Crashes the Job

**What goes wrong:** The setup job parses the dispatch payload and outputs a matrix. If a dispatch for "lambdas" produces a non-empty lambda matrix but empty SF and APGW matrices, and the SF/APGW jobs try to use `strategy: matrix: ${{ fromJson(needs.setup.outputs.sf_matrix) }}`, the job fails with an error because `fromJson` on an empty array `[]` produces an invalid matrix.

**Why it happens:** GHA's `strategy.matrix` does not accept an empty `include` array. It is not treated as "skip this job" -- it is treated as a validation error. The job crashes rather than gracefully skipping.

**Consequences:** Workflow run fails with a cryptic error about invalid matrix. The resource type that *should* deploy also gets blocked if it depends on the crashed job.

**Prevention:**
- Use `if` conditions on each type job to guard against empty matrices *before* the matrix is evaluated: `if: needs.setup.outputs.has_lambdas == 'true'`. The setup job must expose boolean outputs like `has_lambdas`, `has_step_functions`, `has_api_gateways` in addition to or instead of the matrix JSON.
- The `if` condition skips the job entirely, so the matrix expression is never evaluated.
- Do NOT rely on `if: needs.setup.outputs.lambda_matrix != '[]'` alone -- use a dedicated boolean output for clarity and to avoid string comparison edge cases (empty string vs `[]` vs `{"include":[]}`).

**Detection:** Push a change affecting only one resource type. If the other type jobs show red (failed) instead of grey (skipped), this is the cause.

**Confidence:** HIGH -- well-documented issue (https://github.com/orgs/community/discussions/27096).

**Phase:** Setup action changes phase. The parse_payload output must include boolean flags.

---

### Pitfall 4: Workflow File Must Exist on Default Branch Before First Dispatch

**What goes wrong:** The backend dispatches to `ferry.yml` via the GitHub API (`POST /repos/{owner}/{repo}/actions/workflows/ferry.yml/dispatches`). If the user's repo still has only the old per-type workflow files and has not yet merged `ferry.yml` to their default branch, the API returns 404. The backend logs "dispatch failed" but the user sees nothing -- no workflow run, no error on the PR.

**Why it happens:** GitHub's workflow_dispatch API requires the workflow file to exist on the repository's default branch. It does not look at feature branches. This is a fundamental GHA constraint, not a Ferry bug.

**Consequences:** Silent deployment failure. Backend returns 404 for every dispatch. No resources deploy. No error visible in GHA UI because no workflow run was created.

**Prevention:**
- The migration must ensure `ferry.yml` is merged to the default branch *before* the backend starts dispatching to it.
- During migration, the backend should dispatch to the OLD workflow filenames until the user has migrated. This means either:
  (a) A feature flag / config version in `ferry.yaml` that tells the backend which workflow filename to use, OR
  (b) A backend change that tries the new filename first, falls back to old filenames on 404 (adds latency and complexity), OR
  (c) A coordinated cutover: update backend + user repo simultaneously (simplest for single-user/early stage).
- For Ferry's current stage (single test repo, early product), option (c) is fine. Document the migration order: (1) add `ferry.yml` to user repo, (2) update backend dispatch code, (3) delete old workflow files.

**Detection:** Backend logs show 404 status for dispatch calls. No workflow runs appear in the user's Actions tab.

**Confidence:** HIGH -- documented GHA requirement (https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions).

**Phase:** Migration phase. Must be planned explicitly with a cutover procedure.

---

### Pitfall 5: GHA UI Shows 3 Identical Workflow Runs -- Impossible to Distinguish

**What goes wrong:** When a push affects all 3 resource types, the backend sends 3 dispatches to `ferry.yml`. The GHA Actions tab shows 3 workflow runs all named "Ferry Deploy" (or whatever the workflow `name:` is). They all reference the same commit SHA. The user cannot tell which run is for lambdas vs. step functions vs. API gateways without clicking into each one.

**Why it happens:** `workflow_dispatch` runs share the same workflow name. Without a dynamic `run-name`, GHA uses the static workflow `name:` for all runs.

**Consequences:** Debugging is painful. If one type fails, the user must click through all 3 runs to find which one. Repeated pushes create a wall of identically-named runs. User trust in the tool decreases.

**Prevention:**
- Use `run-name` with the `inputs` context to create distinguishable names:
  ```yaml
  run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'unknown' }}"
  ```
- The `run-name` field supports `github` and `inputs` contexts (confirmed in official docs).
- Parse the resource_type from the payload JSON in the `run-name` expression. This is the only way to distinguish runs in the UI.
- Fallback with `|| 'unknown'` prevents broken names if the expression fails.

**Detection:** Look at the Actions tab after a multi-type push. If all runs have the same name, this needs fixing.

**Confidence:** HIGH -- `run-name` with `inputs` context is documented: https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions

**Phase:** Workflow template design phase. Must be in the initial template.

## Moderate Pitfalls

### Pitfall 6: Stale Old Workflow Files Linger in GHA UI

**What goes wrong:** After migrating to `ferry.yml`, the old `ferry-lambdas.yml`, `ferry-step_functions.yml`, and `ferry-api_gateways.yml` files are deleted. But GHA still shows them in the Actions tab sidebar with all their historical runs. The user sees 4 workflows in the sidebar (1 new + 3 old) and gets confused about which is active.

**Why it happens:** GitHub does not provide a way to delete workflow entries from the Actions UI. Deleting the YAML file removes it from the workflow list eventually (after a period), but historical runs persist. There is no API to purge workflow history completely.

**Prevention:**
- Accept this as cosmetic and document it for users: "Old workflow entries will disappear from the sidebar after deletion, but historical runs remain accessible."
- Delete old workflow files in a separate commit with a clear commit message.
- Optionally use `gh api` to delete individual old workflow runs if a clean UI is important, but this is tedious for many runs.
- Do NOT leave old workflow files in the repo "just in case" -- they will confuse users and could receive dispatches if the backend falls back.

**Detection:** After migration, check the Actions tab sidebar. Old workflows should stop appearing in the sidebar (though it may take a few minutes).

**Confidence:** MEDIUM -- based on community reports (https://github.com/orgs/community/discussions/26256, https://github.com/orgs/community/discussions/40350).

**Phase:** Migration/cleanup phase. Low priority, cosmetic.

---

### Pitfall 7: workflow_dispatch Input Payload Size Limit (65,535 chars)

**What goes wrong:** The dispatch payload is passed as a single `inputs.payload` JSON string. If a user has many resources of one type (e.g., 50+ Lambdas all affected by a shared library change), the serialized payload exceeds the 65,535 character GitHub API limit. The dispatch API rejects it.

**Why it happens:** GitHub enforces a hard limit of 65,535 characters across all `workflow_dispatch` inputs. The current code already checks for this (`_MAX_PAYLOAD_SIZE = 65535` in `trigger.py`), but the unified workflow does not change this risk -- it remains the same.

**Consequences:** Dispatch fails silently from the user's perspective (backend logs the 413 but the user sees no workflow run).

**Prevention:**
- The existing payload size check in `trigger.py` already handles this. No change needed for unified workflow.
- For future: if payloads grow, the backend could split large type groups into multiple dispatches (e.g., 2 Lambda dispatches of 25 each). The unified workflow handles this naturally since each dispatch creates a separate run.
- Document the practical limit: approximately 50-80 Lambda resources per dispatch depending on field lengths.

**Detection:** Backend logs show `dispatch_payload_too_large` with status 413.

**Confidence:** HIGH -- existing code already handles this, limit documented by GitHub.

**Phase:** No action needed for v1.4. Already handled. Flag for future scaling.

---

### Pitfall 8: OIDC Token Reuse Across Parallel Jobs in Same Workflow Run

**What goes wrong:** In the unified workflow, if multiple jobs within the same workflow run (e.g., a Lambda build job and a Lambda deploy job) both request OIDC tokens, and the jobs run on different runners, each gets its own token. But if jobs share a runner or if token requests overlap, there can be confusion about which credentials are active.

**Why it happens:** Each job in GHA runs in a fresh runner VM, so OIDC tokens are isolated per job. This is actually safe. The real risk is if someone tries to optimize by sharing credentials across jobs via artifacts or outputs, which would break the OIDC security model.

**Consequences:** If credentials are accidentally shared, the wrong role could be assumed. In practice this is unlikely with the current composite action design since each action call does its own `configure-aws-credentials`.

**Prevention:**
- Each type-specific job must independently call `configure-aws-credentials` with the user's role ARN. The current composite actions already do this.
- Do NOT try to "optimize" by authenticating once in setup and passing credentials to downstream jobs.
- This is a non-issue as long as the existing pattern is preserved, but worth documenting to prevent future "optimization" attempts.

**Detection:** IAM errors in one job type but not others would indicate credential confusion.

**Confidence:** HIGH -- GHA job isolation is well-documented.

**Phase:** Not a code change; just a design principle to maintain.

---

### Pitfall 9: Backend Must Change `workflow_file` Atomically With User Repo

**What goes wrong:** The backend code currently constructs the workflow filename as `f"ferry-{workflow_name}.yml"` (e.g., `ferry-lambdas.yml`). Changing this to `ferry.yml` requires updating the backend. If the backend deploys before the user adds `ferry.yml` (or vice versa), dispatches fail.

**Why it happens:** The backend and user repo are separate codebases with separate deploy cycles. There is no transactional way to update both simultaneously.

**Consequences:** During the gap between backend deploy and user repo update, all dispatches fail with 404. Any pushes during this window result in no deployments.

**Prevention:**
- **Order matters:** (1) User adds `ferry.yml` to their default branch, (2) Backend deploys with new filename. This order ensures the old workflow files still work until the backend switches, and the new file is already in place when the backend starts targeting it.
- **Do NOT deploy backend first.** Old workflow files + new backend = 404 for all dispatches.
- For multi-tenant future: add a version field to `ferry.yaml` (e.g., `workflow_version: 2`) that tells the backend which filename to dispatch to. This allows gradual migration per-repo.
- For v1.4 (single test repo): coordinate manually. Deploy in the documented order.

**Detection:** Backend logs show 404 for dispatch calls after deploy.

**Confidence:** HIGH -- direct analysis of the current codebase (`trigger.py` line 155).

**Phase:** Migration phase. Document the deploy order. Consider a version field for multi-tenant future.

---

### Pitfall 10: `fromJson` Expression Fails If Payload Input Is Empty or Malformed

**What goes wrong:** The `run-name` and `concurrency` fields use expressions like `fromJson(github.event.inputs.payload).resource_type`. If the workflow is triggered manually from the GHA UI (not via API dispatch), `inputs.payload` may be empty or user-provided garbage. The `fromJson` call fails and the workflow name/concurrency group breaks.

**Why it happens:** `workflow_dispatch` allows manual triggers from the GHA UI. Users (or curious developers) may click "Run workflow" without providing valid payload JSON.

**Consequences:** Workflow fails immediately with an expression evaluation error, or the `run-name` shows an error string.

**Prevention:**
- Guard all `fromJson` expressions with a null check: `${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}`
- Add a description to the `payload` input in the workflow that warns it is not intended for manual use.
- The setup job's parse_payload already validates and fails gracefully, so the workflow will fail at the setup step with a clear error. The risk is only in `run-name` and `concurrency` expressions which run before any job starts.

**Detection:** Manual trigger from GHA UI produces immediate workflow failure or garbled run name.

**Confidence:** MEDIUM -- based on `run-name` context limitations in official docs.

**Phase:** Workflow template design phase. Use defensive expressions.

## Minor Pitfalls

### Pitfall 11: Job Names in GHA UI Are Generic Without Explicit `name:`

**What goes wrong:** Without explicit `name:` on each job, GHA shows the job ID (e.g., `deploy-lambdas`) in the UI. This is acceptable but not ideal. With matrix expansion, it shows `deploy-lambdas (order-processor)` which is better but requires the matrix to include a `name` field.

**Prevention:**
- Set explicit `name:` on each job: `name: "Deploy Lambda: ${{ matrix.name }}"` for matrix jobs, `name: "Setup (${{ fromJson(github.event.inputs.payload).resource_type }})"` for the setup job.
- This is existing best practice, not a new requirement.

**Confidence:** HIGH -- standard GHA feature.

**Phase:** Workflow template design phase.

---

### Pitfall 12: `permissions` Must Cover All Job Types

**What goes wrong:** The unified workflow needs `id-token: write` (for OIDC) and `contents: read` (for checkout). If different resource types needed different permissions, the workflow-level permissions block must be the superset. Currently all three types need the same permissions, so this is not an issue today.

**Prevention:**
- Set workflow-level permissions to the superset: `id-token: write`, `contents: read`.
- If future types need different permissions, use job-level `permissions` overrides.
- This is a non-issue for v1.4 but worth noting for extensibility.

**Confidence:** HIGH.

**Phase:** Workflow template design phase. Already correct.

---

### Pitfall 13: Test Coverage Gap During Migration

**What goes wrong:** Existing tests validate the per-type workflow dispatch (backend sends to `ferry-lambdas.yml`, etc.). After changing the backend to dispatch to `ferry.yml`, all existing dispatch tests break because they assert the old workflow filename. If tests are not updated alongside the code, CI goes red and the team loses confidence.

**Prevention:**
- Update `RESOURCE_TYPE_WORKFLOW_MAP` in `constants.py` (or the dispatch logic in `trigger.py`) and update ALL tests that assert workflow filenames in the same commit.
- Search the test suite for strings like `ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml` to find all assertions that need updating.
- Consider parameterizing the workflow filename in tests to make future changes easier.

**Detection:** CI fails after the backend change.

**Confidence:** HIGH -- direct analysis of codebase.

**Phase:** Backend code change phase. Tests must be updated atomically with the dispatch logic.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Workflow template design | Concurrency groups cancel parallel dispatches (Pitfall 1) | No workflow-level concurrency, or scope to resource_type |
| Workflow template design | Run names indistinguishable (Pitfall 5) | Use `run-name` with `fromJson(inputs.payload).resource_type` |
| Workflow template design | Skipped job cascade (Pitfall 2) | Use `!failure() && !cancelled()` for downstream deps |
| Workflow template design | Empty matrix crash (Pitfall 3) | Boolean flags from setup, `if` guard before matrix |
| Workflow template design | Manual trigger breaks expressions (Pitfall 10) | Defensive `fromJson` with fallback `|| 'manual'` |
| Setup action changes | parse_payload must output booleans for job routing (Pitfall 3) | Add `has_lambdas`, `has_step_functions`, `has_api_gateways` outputs |
| Backend dispatch change | Workflow filename change breaks tests (Pitfall 13) | Update constants + all test assertions atomically |
| Migration / cutover | Deploy order matters (Pitfalls 4, 9) | User adds `ferry.yml` first, then backend deploys |
| Migration / cutover | Old workflows linger in UI (Pitfall 6) | Document, accept as cosmetic, delete old files |
| Future scaling | Payload size limit (Pitfall 7) | Already handled; split dispatches if needed later |

## Sources

- [GitHub Docs: Workflow syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions) -- workflow_dispatch limits, run-name, concurrency syntax (HIGH confidence)
- [GitHub Docs: Control concurrency](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) -- concurrency group behavior (HIGH confidence)
- [GitHub Docs: Using conditions for job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) -- if conditions, needs behavior (HIGH confidence)
- [Community Discussion: Concurrency race condition](https://github.com/orgs/community/discussions/9252) -- concurrency group race conditions (MEDIUM confidence)
- [Community Discussion: cancel-in-progress bug](https://github.com/orgs/community/discussions/53506) -- cancel-in-progress kills pending workflows (MEDIUM confidence)
- [Community Discussion: success() returns false when needed job skipped](https://github.com/orgs/community/discussions/45058) -- skipped job dependency chain (MEDIUM confidence)
- [Runner Issue: Job-level if with skipped needs](https://github.com/actions/runner/issues/491) -- skipped job cascade behavior (MEDIUM confidence)
- [Community Discussion: Dynamic matrix empty array](https://github.com/orgs/community/discussions/27096) -- fromJson empty array crash (MEDIUM confidence)
- [Community Discussion: Delete old workflows](https://github.com/orgs/community/discussions/26256) -- old workflow cleanup limitations (MEDIUM confidence)
- [Community Discussion: workflow_dispatch inputs limits](https://github.com/orgs/community/discussions/120093) -- 25 inputs, 65535 chars (MEDIUM confidence)
- [GitHub Changelog: Dynamic run names](https://github.blog/changelog/2022-09-26-github-actions-dynamic-names-for-workflow-runs/) -- run-name feature (HIGH confidence)
- [DevOps Directive: Required checks for conditional jobs](https://devopsdirective.com/posts/2025/08/github-actions-required-checks-for-conditional-jobs/) -- skipped jobs and branch protection (MEDIUM confidence)
- Direct codebase analysis: `trigger.py`, `constants.py`, `parse_payload.py`, composite actions (HIGH confidence)
