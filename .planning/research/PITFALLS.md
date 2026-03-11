# Domain Pitfalls: Batched Dispatch for Ferry v1.5

**Domain:** Adding batched/multi-type dispatch to existing per-type dispatch system in GitHub Actions
**Project:** Ferry v1.5 (Batched Dispatch)
**Researched:** 2026-03-10
**Overall confidence:** HIGH (pitfalls derived from reading actual codebase + verified GHA platform constraints)

---

## Critical Pitfalls

Mistakes that cause broken deployments, silent failures, or require rearchitecting the approach.

---

### Pitfall 1: Empty Matrix Crashes the Workflow -- fromJson with Zero Elements

**What goes wrong:** When the batched payload contains resources for some types but not others, the setup job must output separate matrices per type (e.g., `lambda_matrix`, `step_function_matrix`, `api_gateway_matrix`). If a type has no affected resources, its matrix output is `{"include":[]}`. When a deploy job does `strategy: matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}`, GHA throws: `"Matrix vector does not contain any values"` and the entire workflow fails -- not just the empty job.

**Why it happens:** GHA evaluates `strategy.matrix` before checking the job's `if` condition in some execution paths. Even if `if:` would skip the job, the matrix expression can be evaluated and fail first. This is a known GHA platform bug/quirk documented in [community discussion #27096](https://github.com/orgs/community/discussions/27096).

**Consequences:** A push that only changes Lambdas crashes the entire workflow because the Step Functions matrix is empty. All deploys blocked, including the Lambdas that should have deployed.

**Prevention:**
1. The setup action must output a boolean flag per type (e.g., `has_lambdas`, `has_step_functions`, `has_api_gateways`) in addition to the matrix JSON.
2. Each deploy job must guard with `if: needs.setup.outputs.has_lambdas == 'true'` -- this is evaluated before the matrix expression.
3. Also guard the matrix value itself: `matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix || '{"include":[{"skip":"true"}]}') }}` as a belt-and-suspenders fallback. But the `if:` guard is primary.
4. Test all combinations: only-lambdas, only-SF, only-APGW, lambdas+SF, all-three, none (edge case: push detected changes but all were filtered out).

**Detection:** Workflow fails on setup/matrix evaluation step with "does not contain any values" error. Easy to miss in local testing because you always test with at least one resource per type.

**Phase assignment:** Must be addressed in the setup action changes (first phase). This is a day-one blocker.

---

### Pitfall 2: Payload Size Explosion When Batching All Types

**What goes wrong:** Currently, each per-type dispatch carries only the resources of that type. A batched dispatch puts ALL types into a single JSON payload sent as a single `workflow_dispatch` input value. The combined payload for a repo with 20 Lambdas + 5 Step Functions + 3 API Gateways could exceed GHA limits.

**Why it happens:** GHA `workflow_dispatch` has two relevant limits:
- **Per-input value:** Reports vary -- some sources say 1024 chars for UI-triggered dispatches, but API-triggered dispatches (which Ferry uses) appear to allow up to 65,535 chars based on the existing `_MAX_PAYLOAD_SIZE` constant in `trigger.py`.
- **Total inputs payload:** 65,535 characters across all inputs combined.

The current per-type payload for 2-3 resources is roughly 300-500 bytes. A batched payload for 20+ resources across 3 types could be 5,000-10,000 bytes -- still well under 65K. But edge cases matter: repos with many resources, long names, long source paths, or verbose config fields.

**Consequences:** Silent truncation or API 422 error. The backend thinks it dispatched successfully but the workflow receives corrupted JSON. Parse fails in setup action, entire workflow fails. Currently the backend already checks `_MAX_PAYLOAD_SIZE` but only per-type -- the batched payload is larger.

**Prevention:**
1. Keep the existing `_MAX_PAYLOAD_SIZE = 65535` check, but apply it to the combined batched payload.
2. Calculate realistic worst-case: 50 resources * ~200 bytes each = ~10KB. Safe margin but not infinite.
3. Add a fallback: if batched payload exceeds threshold (e.g., 50KB), fall back to per-type dispatches. Log a warning. This preserves the current behavior as a safety net.
4. Add a unit test that constructs a payload with 100 resources and verifies it stays under the limit (or triggers the fallback).

**Detection:** Backend logs `dispatch_payload_too_large`. Action logs `Failed to parse dispatch payload`. Both already exist in current code.

**Phase assignment:** Address in the payload schema redesign phase. The fallback-to-per-type logic should be in the same phase as the batched dispatch trigger.

---

### Pitfall 3: Breaking the `if: resource_type == 'lambda'` Guard Pattern

**What goes wrong:** The current `ferry.yml` uses `if: needs.setup.outputs.resource_type == 'lambda'` to route to the correct deploy job. In the batched model, there is no single `resource_type` -- the payload contains multiple types. If the setup action still outputs `resource_type` as a single string, only one type's job runs per dispatch.

**Why it happens:** The existing `parse_payload.py` extracts `resource_type` from the payload and sets it as a single output (`set_output("resource_type", payload.resource_type)`). The entire conditional routing in `ferry.yml` depends on this being a single value. Batched dispatch fundamentally breaks this assumption.

**Consequences:** Only one resource type deploys per push. The other types silently skip. Users see "skipped" jobs in GHA UI and assume everything is fine, but resources are not deploying. This is the worst kind of failure: silent and correctness-breaking.

**Prevention:**
1. Replace the single `resource_type` output with per-type boolean flags: `has_lambdas`, `has_step_functions`, `has_api_gateways`.
2. Replace the single `matrix` output with per-type matrices: `lambda_matrix`, `step_function_matrix`, `api_gateway_matrix`.
3. Update each deploy job's `if:` condition from `needs.setup.outputs.resource_type == 'lambda'` to `needs.setup.outputs.has_lambdas == 'true'`.
4. Update each deploy job's `strategy.matrix` from `fromJson(needs.setup.outputs.matrix)` to `fromJson(needs.setup.outputs.lambda_matrix)`.
5. The setup action must be updated atomically with the workflow template. A mismatch (new setup action + old `ferry.yml`, or old setup action + new `ferry.yml`) guarantees breakage.

**Detection:** Jobs marked as "skipped" in GHA UI when they should have run. Hard to detect without integration tests.

**Phase assignment:** Core change -- must be in the first implementation phase. The setup action and ferry.yml template must change together.

---

### Pitfall 4: Concurrency Group Conflicts Between Types in a Single Run

**What goes wrong:** The current `ferry.yml` has per-job concurrency groups: `ferry-deploy-lambda`, `ferry-deploy-step-function`, `ferry-deploy-api-gateway`. With per-type dispatch, each workflow run only has one active deploy job, so there is no conflict. With batched dispatch, a single workflow run can have all three deploy jobs active simultaneously. If two pushes happen in quick succession, the second run's Lambda job might cancel the first run's Lambda job (correct), but the concurrency group could also interfere with jobs of different types in the same run (incorrect).

**Why it happens:** GHA concurrency groups are global within the repository. The group `ferry-deploy-lambda` correctly serializes Lambda deploys across runs. But if you accidentally share a concurrency group between types (or use a workflow-level concurrency group), you get unexpected cancellations.

**Consequences:** In the best case, deploys are serialized when they should be parallel (slow). In the worst case, a Lambda deploy cancels a Step Function deploy because they share a concurrency group.

**Prevention:**
1. Keep the existing per-type concurrency groups exactly as they are: `ferry-deploy-lambda`, `ferry-deploy-step-function`, `ferry-deploy-api-gateway`. Do NOT add a workflow-level concurrency group.
2. Do NOT add `cancel-in-progress: true` to any deploy job. The current `cancel-in-progress: false` is correct -- you want queuing, not cancellation.
3. Verify that within a single workflow run, jobs with different concurrency groups run in parallel (they do -- GHA concurrency groups only serialize across runs, not within a run).
4. Consider whether the concurrency group should include a resource identifier for finer-grained serialization (e.g., `ferry-deploy-lambda-${{ matrix.function_name }}`), but this is a future optimization, not a v1.5 requirement.

**Detection:** Unexpected "cancelled" status on deploy jobs. Jobs that should run in parallel running sequentially.

**Phase assignment:** Review during the workflow template update phase. Mostly a "don't break what works" concern.

---

## Moderate Pitfalls

Issues that cause confusing behavior, wasted CI time, or require manual intervention but do not break deployments.

---

### Pitfall 5: Backward Incompatible Payload Schema Breaks Mid-Migration

**What goes wrong:** The backend starts sending batched payloads (new schema), but the user's `ferry.yml` in their repo still expects the old per-type schema. The setup action on `main` in the user's repo is the OLD setup action that expects `DispatchPayload` with a single `resource_type`. It receives a batched payload and fails to parse it.

**Why it happens:** Ferry has a split deployment model:
- **Backend**: Deployed by the Ferry team (single Lambda, updated instantly).
- **Setup Action**: Referenced from the Ferry repo (`AmitLaviDev/ferry/action/setup@main`), but...
- **Workflow file**: Lives in the USER's repo. Updated by the user when they choose.

If the backend sends a new payload format before the user updates their `ferry.yml` (which references the setup action), deployments break. Even if the setup action is updated (it comes from the Ferry repo, not the user's repo), the `ferry.yml` `if:` guards and `matrix:` expressions still reference the old output names.

**Consequences:** All deployments fail for all Ferry users simultaneously when the backend is updated. There is no gradual rollout.

**Prevention:**
1. **Schema version field**: The `DispatchPayload` already has a `v` field (currently `v: 1`). Bump to `v: 2` for batched payloads.
2. **Backward-compatible setup action**: The updated setup action must handle BOTH `v: 1` (per-type) and `v: 2` (batched) payloads. When it receives `v: 1`, produce outputs in the old format (single `matrix`, single `resource_type`). When it receives `v: 2`, produce outputs in the new format (per-type matrices, per-type boolean flags).
3. **Dual-output period**: During migration, the setup action outputs BOTH old-format and new-format outputs. Old `ferry.yml` files that check `resource_type` still work. New `ferry.yml` files that check `has_lambdas` also work.
4. **Deploy order**: (a) Update setup action to handle both schemas. (b) Update Ferry backend to send batched payloads. (c) Update the documented `ferry.yml` template. (d) Users migrate at their pace.
5. **Feature flag**: Consider a per-repo flag (e.g., in `ferry.yaml`: `dispatch_mode: batched`) that the backend checks before deciding to send batched vs. per-type payloads. This is more complex but allows per-user migration.

**Detection:** Backend returns 204 (dispatch accepted) but the workflow fails in the setup step. Monitor GHA workflow run status via the API after dispatching.

**Phase assignment:** Must be addressed in payload schema design (first phase). The migration strategy determines the entire implementation order.

---

### Pitfall 6: Job Dependency Graph Breaks When `needs` Jobs Are Skipped

**What goes wrong:** In the current `ferry.yml`, all three deploy jobs `needs: setup`. With per-type dispatch, exactly one deploy job runs and two are skipped. There are no downstream jobs that depend on the deploy jobs, so this is fine. But if you add a summary/notification job that `needs: [deploy-lambda, deploy-step-function, deploy-api-gateway]`, it will be skipped when ANY of its dependencies are skipped -- which is always, since at most 2 of 3 are active.

**Why it happens:** GHA's default behavior: if any job in the `needs` list is skipped, the dependent job is also skipped -- unless it uses `if: always()` or `if: ${{ !failure() && !cancelled() }}`. This is documented in [actions/runner#491](https://github.com/actions/runner/issues/491).

**Consequences:** Any "post-deploy" job (summary, notification, status update) never runs. If you add `if: always()`, it becomes uncancellable. If you use `if: ${{ !failure() && !cancelled() }}`, it runs even when some deploy jobs fail.

**Prevention:**
1. For v1.5, do NOT add a post-deploy summary job. Keep the existing flat structure.
2. If a post-deploy job is needed later (e.g., for v2.0 PR integration), use: `if: ${{ !cancelled() && (needs.deploy-lambda.result == 'success' || needs.deploy-lambda.result == 'skipped') && ... }}` for each dependency.
3. Document this GHA quirk in the ferry.yml template comments so users don't add downstream jobs naively.

**Detection:** Summary/notification jobs showing as "skipped" in GHA UI when deploys succeeded.

**Phase assignment:** Not a v1.5 concern unless adding post-deploy jobs. Document as a known constraint.

---

### Pitfall 7: `run-name` Expression Breaks with Batched Payload

**What goes wrong:** The current `ferry.yml` has:
```yaml
run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}"
```
With a batched payload, `.resource_type` is either removed or becomes a list. The `run-name` expression evaluates to something unexpected or errors out.

**Why it happens:** The `run-name` expression is evaluated at workflow start, before any job runs. It accesses the raw dispatch input directly. If the payload schema changes, this expression must change too.

**Consequences:** Cosmetic: the workflow run name in GHA UI shows "manual" or a raw JSON fragment instead of a meaningful name. Not a functional break, but confusing for users scanning their workflow history.

**Prevention:**
1. For batched payloads, add a `summary` field to the payload (e.g., `"lambda,step_function"` or `"3 resources"`).
2. Update `run-name` to use the summary field: `"Ferry Deploy: ${{ fromJson(github.event.inputs.payload).summary || 'manual' }}"`.
3. Make the summary human-readable: `"2 lambdas, 1 step function"` reads better in the GHA UI.
4. Keep a fallback for `v: 1` payloads that still have `resource_type`.

**Detection:** Visual inspection of the workflow run list in GHA.

**Phase assignment:** Address in the workflow template update phase. Low priority but easy to forget.

---

### Pitfall 8: Test Matrix Combinatorial Explosion

**What goes wrong:** The current test suite tests per-type dispatch in isolation. Batched dispatch introduces combinatorial complexity: 3 types with presence/absence = 8 combinations. Add in "resources present but all skipped by content-hash" and the matrix grows further. Tests that worked for single-type dispatch miss multi-type edge cases.

**Why it happens:** Per-type dispatch has clean boundaries: each dispatch is independent. Batched dispatch couples all types into a single flow. The setup action must handle all combinations correctly, and the workflow must route correctly for each.

**Consequences:** Untested combinations fail in production. Common scenario: "Lambda + APGW works, Lambda + SF works, but Lambda + SF + APGW fails because the matrix JSON exceeds the GITHUB_OUTPUT line length limit."

**Prevention:**
1. Enumerate the 8 type combinations explicitly in tests: `{L, SF, APGW, L+SF, L+APGW, SF+APGW, L+SF+APGW, none}`.
2. For each combination, test: (a) payload serialization, (b) setup action output correctness, (c) per-type boolean flags, (d) per-type matrix JSON validity.
3. Add a "large payload" test: 20 Lambdas + 5 SF + 3 APGW. Verify total output size stays under GITHUB_OUTPUT limits (1MB per job).
4. Add an integration test (or at minimum a documented manual test) that runs the actual `ferry.yml` workflow with a batched payload. This cannot be fully automated in pytest but a test payload file can be prepared.

**Detection:** CI passes but real workflows fail. The gap between unit tests and GHA execution is the danger zone.

**Phase assignment:** Must be addressed alongside the setup action changes. Test coverage is a gate for merging the setup action update.

---

## Minor Pitfalls

Issues that are annoying but have straightforward fixes.

---

### Pitfall 9: GITHUB_OUTPUT Multiline Value Handling

**What goes wrong:** The current `gha.set_output()` uses the simple `name=value` format. If any matrix JSON value contains newlines (unlikely but possible with malformed resource names or paths), the output is silently truncated at the first newline.

**Prevention:** Use the heredoc delimiter format for GITHUB_OUTPUT when values might contain newlines:
```
{name}<<{delimiter}
{value}
{delimiter}
```
The current code works because matrix JSON is single-line (compact serialization with `separators=(",",":")}`). Verify that the batched payload maintains this property. The `model_dump_json()` method in Pydantic uses compact serialization by default, so this should be fine.

**Phase assignment:** Verify during implementation. No code change needed if compact serialization is maintained.

---

### Pitfall 10: Step Function and API Gateway Sequential Deploy Assumptions

**What goes wrong:** In the current system, SF and APGW deploys use `fail-fast: false` in their matrix strategy but implicitly only run one resource at a time (typical repos have 1 SF, 1 APGW). With batched dispatch, if a user has multiple SF resources, they deploy in parallel within the matrix. If those SFs have ordering dependencies (e.g., SF-A calls SF-B), parallel deploy could leave the system in an inconsistent state.

**Prevention:** This is NOT a v1.5 concern -- it exists in the per-type model too. But batched dispatch makes it more visible because all three types deploy in one run. Document in the `ferry.yml` template that resources within a type deploy in parallel. Users who need sequential deploys must use the `concurrency` group at a finer grain or split into separate ferry.yaml entries.

**Phase assignment:** Documentation update only.

---

### Pitfall 11: Pydantic Discriminated Union with Mixed Resource Types

**What goes wrong:** The current `DispatchPayload.resources` uses a discriminated union on `resource_type` field. Each resource in the list is validated against its specific type. The existing test `test_mixed_resource_types_in_single_payload` already demonstrates that the Pydantic model allows mixed types in a single payload -- but the `_MATRIX_BUILDERS` dict in `parse_payload.py` filters by `isinstance`, so only the matching type's resources are extracted.

In a batched payload, the resources list WILL contain mixed types. The current `build_matrix()` function uses `payload.resource_type` to select a single builder. With batched dispatch, there is no single `resource_type` -- the function must iterate all builders and produce separate matrices.

**Prevention:**
1. Refactor `build_matrix()` to return a dict of matrices keyed by type, not a single matrix.
2. Or: change the payload schema so resources are grouped by type at the top level (e.g., `lambdas: [...]`, `step_functions: [...]`), matching the `ferry.yaml` structure. This is cleaner for the action side.
3. Either way, the setup action output changes from one `matrix` to three per-type matrices.

**Phase assignment:** Core change in the setup action. Address in the first implementation phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Payload schema redesign | Pitfall 5 (backward compatibility), Pitfall 2 (size limits) | Version field, dual-schema support, size check with fallback |
| Setup action changes | Pitfall 1 (empty matrix), Pitfall 3 (routing guards), Pitfall 11 (mixed types) | Per-type boolean flags, per-type matrices, refactored build_matrix |
| Workflow template update | Pitfall 4 (concurrency groups), Pitfall 7 (run-name), Pitfall 6 (needs/skipped) | Keep per-type groups, update run-name expression, avoid post-deploy jobs |
| Backend dispatch changes | Pitfall 2 (payload size), Pitfall 5 (migration timing) | Size check, fallback to per-type, deploy setup action first |
| Testing | Pitfall 8 (combinatorial explosion) | Enumerate all 8 type combinations, large payload test, integration test plan |
| Migration / rollout | Pitfall 5 (backward compatibility) | Deploy in order: setup action, backend, template docs. Schema version gating. |

## Implementation Order Recommendation

Based on pitfall analysis, the safest implementation order is:

1. **Setup action first**: Make it handle both v1 (per-type) and v2 (batched) payloads. Ship this before anything else. It is backward-compatible by definition (v1 payloads still produce old-format outputs).
2. **Backend dispatch second**: Switch to batched payloads. If the setup action handles both schemas, this is safe to deploy.
3. **Workflow template third**: Update the documented `ferry.yml` to use per-type matrices and boolean flags. Users migrate at their pace because the setup action's dual-output mode supports both old and new `ferry.yml` formats.

This order ensures no single deployment breaks existing users.

## Sources

- [GHA Community: Empty matrix crash](https://github.com/orgs/community/discussions/27096) -- empty `fromJson` matrix error
- [GHA Community: workflow_dispatch input limits](https://github.com/orgs/community/discussions/120093) -- per-input and total payload limits
- [GHA Changelog: 25 inputs](https://github.blog/changelog/2025-12-04-actions-workflow-dispatch-workflows-now-support-25-inputs/) -- input count limit increase
- [GHA Runner Issue: Skipped job dependencies](https://github.com/actions/runner/issues/491) -- `needs` + skipped job behavior
- [GHA Community: Skipped job cascading](https://github.com/orgs/community/discussions/26945) -- `needs` + `if` interaction
- [GHA Community: Concurrency group scope](https://github.com/orgs/community/discussions/78332) -- concurrency group scoping
- [GHA Docs: Concurrency control](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) -- official concurrency documentation
- Ferry codebase: `backend/src/ferry_backend/dispatch/trigger.py`, `action/src/ferry_action/parse_payload.py`, `action/setup/action.yml`, `docs/setup.md`
