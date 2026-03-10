# Project Research Summary

**Project:** Ferry v1.5 Batched Dispatch
**Domain:** GitHub Actions dispatch consolidation for serverless deploy tool
**Researched:** 2026-03-10
**Confidence:** HIGH

## Executive Summary

Ferry v1.5 replaces per-type `workflow_dispatch` (up to 3 dispatches per push) with a single batched dispatch carrying all affected resource types in one payload. This is a targeted, surgical change across 4 layers: the Pydantic dispatch model (`BatchedDispatchPayload` v2), the backend dispatch loop in `trigger.py` (N POSTs become 1), the setup action's `parse_payload.py` (single-type matrix becomes per-type matrix outputs + boolean flags), and the user's `ferry.yml` template (string equality checks become boolean checks). No new libraries or dependencies are introduced. Every piece of this change touches existing code that is already well-understood and tested.

The recommended approach is a strict 4-phase build order driven by dependency flow: shared models first (both backend and action import from them), backend and action changes in parallel second (they are independent of each other), updated workflow template and docs third (depends on knowing the output names from phase 2), and E2E validation fourth. The key GHA behavioral constraints are all HIGH-confidence verified: `if:` conditions prevent `fromJson` evaluation on empty matrices, boolean string comparison (`== 'true'`) is the correct pattern for job gating, multiple deploy jobs with `needs: setup` and no cross-dependency run in parallel, and job-level concurrency groups with `cancel-in-progress: false` correctly serialize same-type deploys across rapid pushes.

The primary risk is not technical — it is the migration cutover order. The user's `ferry.yml` workflow file must be merged to the default branch before the backend is deployed with batched dispatch. Reversed order results in 404 dispatches with no visible error to the user. Secondary risks are the empty-matrix crash (addressed by boolean flags) and the skipped-job cascade problem for any future downstream reporting jobs (addressed by using `!failure() && !cancelled()` instead of implicit `success()`). The skipped-job visual noise for single-type pushes is irreducible with GHA's static job model — 0-2 skipped jobs will remain visible, but the primary UX win (3 runs to 1 run for multi-type pushes) is fully achievable.

## Key Findings

### Recommended Stack

No new dependencies. This is purely a restructuring of existing code. The current stack — Python 3.14, Pydantic v2, boto3, httpx, GHA composite actions — handles everything v1.5 requires. The key change is the schema version bump (`SCHEMA_VERSION = 2` in `constants.py`) and the addition of `BatchedDispatchPayload` to the existing `dispatch.py` models file.

**Core technologies (unchanged):**
- Python 3.14: All backend and action logic — already in use
- Pydantic v2: Dispatch payload models — `resource_type: str` replaced by named type lists (`lambdas`, `step_functions`, `api_gateways`) in new `BatchedDispatchPayload`; old `DispatchPayload` retained for v1 backward compat
- GitHub Actions composite actions: Setup action emits 9 outputs (3 booleans + 3 matrix JSONs + resource_types + 2 legacy); no structural change to how composite actions work
- Ferry codebase (`trigger.py`, `parse_payload.py`, `action.yml`): Direct modification only, no architectural change

**Full detail:** `.planning/research/STACK.md`

### Expected Features

**Must have (table stakes):**
- Single dispatch per push — one `workflow_dispatch` regardless of how many types changed
- All affected types deploy in one workflow run — lambdas, SFs, and APGW all active in the same run when all change
- Only relevant deploy jobs activate — boolean flags (`has_lambdas`, `has_step_functions`, `has_api_gateways`) gate each job with no empty-matrix crash risk
- Per-type matrix fan-out preserved — each deploy job still gets its own typed matrix; parallel resource deployment within each type unchanged
- Content-hash skip detection unchanged — no change needed inside deploy actions
- Payload schema versioned — `v=2` field, backward compatibility for v1 payloads during rollout
- Dynamic `run-name` shows all affected types — "Ferry: lambda, step_function" for multi-type pushes

**Should have (differentiators — polish items):**
- Ordered cross-type deploys — deploy Lambda before SF before APGW when all three change; respects dependency chain
- Aggregated status reporting — one Check Run summary covering all types in the push
- Graceful degradation for oversized payloads — fall back to per-type dispatch if combined payload exceeds 65,535 chars (extreme edge case)

**Defer (v2+):**
- Ordered cross-type deploys — not needed for v1.5; types deploy independently in parallel; add in v2.0
- Aggregated status reporting — each deploy job posts its own Check Run; a summary job is a polish item for v2.0
- Eliminating skipped-job UI noise entirely — not possible with GHA's static job model; accepted limitation; 0-2 skipped jobs remain for single-type pushes

**Full detail:** `.planning/research/FEATURES.md`

### Architecture Approach

The architecture is a clean replacement of the N-dispatch fan-out in `trigger.py` with a single batched payload construction, paired with a mirrored expansion in `parse_payload.py` that fans back out to per-type matrices for the workflow. The payload model uses named type lists (`lambdas: list[LambdaResource]`, etc.) instead of a flat discriminated union, making both serialization and the parse-side matrix building simpler. The `v` field enables version-aware parsing for zero-downtime upgrades. The workflow template structure is nearly identical to v1.4 — only the `if:` conditions and matrix output references change.

**Major components:**
1. `BatchedDispatchPayload` (dispatch.py) — new Pydantic model with named type lists; `DispatchPayload` retained for backward compat; schema v=2
2. `trigger.py: trigger_dispatch()` — replaces `trigger_dispatches()` loop; one payload constructed for all types, one HTTP POST to `ferry.yml`
3. `parse_payload.py: build_batched_outputs()` — replaces `build_matrix()`; outputs 9 GITHUB_OUTPUT values: `has_lambdas`, `has_step_functions`, `has_api_gateways`, `lambda_matrix`, `sf_matrix`, `ag_matrix`, `resource_types`; version-aware `main()` routes v1 vs v2 payloads
4. `setup/action.yml` — declares all 9 new outputs plus 2 legacy outputs (`matrix`, `resource_type`)
5. `ferry.yml` template — boolean-gated jobs (`if: needs.setup.outputs.has_lambdas == 'true'`) with per-type matrix references (`fromJson(needs.setup.outputs.lambda_matrix)`)

**Full detail:** `.planning/research/ARCHITECTURE.md`

### Critical Pitfalls

1. **Migration cutover order** — User must merge `ferry.yml` to default branch BEFORE deploying the backend with batched dispatch. Reversed order = 404 dispatches with no user-visible error. Mitigation: document explicit order; for v1.5 (single test repo) coordinate manually.

2. **Empty matrix crash from `fromJson`** — GHA crashes when `strategy.matrix` receives `{"include":[]}`. Mitigation: boolean flag outputs (`has_lambdas == 'true'`) gate each job; GHA evaluates `if:` before `strategy.matrix` so a false guard prevents matrix evaluation entirely. Do NOT rely on string comparison like `lambda_matrix != '{"include":[]}'` — use the dedicated boolean.

3. **Workflow-level concurrency groups cancel parallel dispatches** — With batched dispatch, each push produces only one dispatch so this risk is eliminated. But per-type job-level concurrency groups must still be used (not workflow-level) to correctly serialize rapid consecutive pushes of the same type.

4. **Skipped job cascade kills downstream dependencies** — Any future summary/gate job that `needs:` all three type jobs will skip when any type job skips (GHA's implicit `success()` returns false for skipped). Mitigation: use `if: ${{ !failure() && !cancelled() }}` on downstream jobs; or keep type jobs as terminal with no downstream dependents (current design).

5. **Test assertions break when dispatch signature changes** — All tests asserting `trigger_dispatches()` (plural, returns list) must be updated to `trigger_dispatch()` (singular, returns dict), and all assertions on workflow filenames updated atomically. Mitigation: update `constants.py`, `trigger.py`, and all test files in the same commit.

**Full detail:** `.planning/research/PITFALLS.md`

## Implications for Roadmap

The dependency graph dictates a clear 4-phase structure. The shared model is the foundation everything else imports; backend and action changes are independent of each other; the workflow template cannot be finalized until output names are known from the action changes; E2E validation must come last.

### Phase 1: Shared Models + Constants

**Rationale:** `BatchedDispatchPayload` and `SCHEMA_VERSION = 2` are imported by both the backend and the action. Neither can be written until this model exists. This is the foundation that unblocks all other phases.
**Delivers:** `BatchedDispatchPayload` Pydantic model with named type lists, schema version 2, updated `__init__.py` re-exports, model unit tests (`test_dispatch_models.py`)
**Addresses:** Payload schema versioning (table stakes), backward compatibility requirement
**Avoids:** Import errors in phase 2 work; forces clean model design before implementation details

### Phase 2a: Backend Dispatch (parallel with 2b)

**Rationale:** Independent of the action changes. `trigger.py` imports the model from phase 1 and calls the GitHub API — no dependency on `parse_payload.py`.
**Delivers:** `trigger_dispatch()` (singular) replacing `trigger_dispatches()` loop; `handler.py` call site update; all dispatch tests rewritten for single-dispatch model; return type simplified from `list[dict]` to `dict`
**Addresses:** Single dispatch per push (primary table stakes), reduces dispatches from N to 1
**Avoids:** Pitfall 5 (test assertions break) — test files updated atomically with the code change

### Phase 2b: Action Parse (parallel with 2a)

**Rationale:** Independent of the backend changes. `parse_payload.py` imports the model from phase 1 and writes to `GITHUB_OUTPUT` — no dependency on `trigger.py`.
**Delivers:** `build_batched_outputs()` function, version-aware `main()` routing (v1 legacy path preserved), all 9 new `action.yml` output declarations, `test_parse_payload.py` tests for batched output generation and v1 compat
**Addresses:** Per-type matrix outputs, boolean flags, `resource_types` string for run-name
**Avoids:** Pitfall 2 (empty matrix crash) — boolean flags are the guard; Pitfall 1 migration order — v1 backward compat means action can deploy before backend without breaking existing v1 payloads

### Phase 3: Workflow Template + Docs

**Rationale:** The `ferry.yml` template references specific output names (`has_lambdas`, `lambda_matrix`, `resource_types`) that are finalized in phase 2b. The docs update mirrors the template change. Both are low-risk, no-test changes.
**Delivers:** Updated `ferry.yml` template with boolean gates and per-type matrix references; updated `docs/setup.md` with new template and dispatch description; `run-name` showing all affected types
**Addresses:** Dynamic run-name (table stakes), job gating correctness, documentation accuracy
**Avoids:** Pitfall 3 (workflow-level concurrency cancels dispatches) — job-level groups with hardcoded type names; Pitfall 4 (indistinguishable run names) — run-name shows all affected types; malformed payload in run-name — defensive `fromJson` with fallback `|| 'manual'`

### Phase 4: Test Repo + E2E Validation

**Rationale:** Must be last. Requires backend with batched dispatch deployed AND test repo with new `ferry.yml` on default branch. Migration cutover order must be followed: test repo update first, then backend deploy.
**Delivers:** Test repo `ferry.yml` updated to v1.5 template; backend deployed; push multi-type change and verify single workflow run with all 3 deploy jobs active; push single-type change and verify 1 active + 2 skipped
**Addresses:** Full-chain validation of the 3-runs-to-1-run UX improvement
**Avoids:** Pitfall 1 migration order — test repo `ferry.yml` merged to main before backend deploys with batched dispatch target

### Phase Ordering Rationale

- Phases 2a and 2b can be built in parallel since they share no imports with each other — only both depend on phase 1 models. In a single-developer context they are sequential but are logically independent PRs.
- Phase 3 is intentionally last among code changes because the exact output key names (`has_lambdas`, `lambda_matrix` etc.) are implementation details of phase 2b — finalizing template after implementation avoids churn.
- Phase 4 validates the full chain. Attempting E2E before all code changes are deployed risks diagnosing phantom bugs from version mismatches.

### Research Flags

No phases require `gsd:research-phase`. All patterns are verified at HIGH confidence.

Phases with well-documented patterns (no additional research needed):
- **Phase 1:** Pydantic v2 model addition — standard pattern, no research needed
- **Phase 2a:** `trigger.py` refactor — direct code change, no new external APIs
- **Phase 2b:** `parse_payload.py` expansion — direct code change; `GITHUB_OUTPUT` format and composite action output pattern are identical to existing code
- **Phase 3:** YAML template update — all GHA patterns (boolean `if:`, per-type matrices, run-name expressions) fully researched and HIGH confidence verified
- **Phase 4:** E2E validation — follow the cutover order documented in Pitfall 1 prevention; no research needed, repeat v1.4 E2E pattern

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies; all changes are to existing, understood code; model design has explicit code samples |
| Features | HIGH | Table stakes are clear and complete; differentiators explicitly deferred with rationale; comparison against Digger/Atlantis confirms novel approach |
| Architecture | HIGH | `BatchedDispatchPayload` design is explicit with code samples; full data flow (backend to GHA to deploy) is mapped end-to-end; all GHA behaviors verified from official docs |
| Pitfalls | HIGH | All critical pitfalls sourced from GitHub official docs or HIGH-confidence community discussions with multiple confirmations |

**Overall confidence:** HIGH

### Gaps to Address

- **Job-level concurrency groups using `needs` outputs** — FEATURES.md flags this as unverified (LOW confidence). Currently concurrency groups use hardcoded type names (`ferry-deploy-lambda`) not dynamic values, so this gap does not affect the v1.5 design. No action needed unless dynamic group names are required in the future.
- **Ordered cross-type deploys** — Deferred to v2.0. The dependency graph (lambda → SF → APGW) is intuitive but not validated against real multi-type deploy scenarios. When implementing in v2.0, verify that downstream `needs:` on conditional jobs requires the `!failure() && !cancelled()` pattern (Pitfall 4 in this research).
- **Aggregated status reporting** — Deferred. The `if: always()` vs `if: ${{ !failure() && !cancelled() }}` choice for a final summary job needs careful testing since it involves skipped-job dependency behavior (well-documented but requires explicit validation in the target repo).

## Sources

### Primary (HIGH confidence)
- Ferry codebase: `trigger.py`, `parse_payload.py`, `dispatch.py`, `constants.py`, `handler.py`, `setup/action.yml`, `ferry.yml` template — all directly read and analyzed
- [GitHub Docs: Workflow syntax](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) — run-name, concurrency, workflow_dispatch input limits (65,535 chars, 25 inputs), `if:` conditional syntax
- [GitHub Docs: Control concurrency](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) — job-level vs workflow-level groups, cancel-in-progress behavior
- [GitHub Docs: Using conditions for job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) — `if:` evaluated before matrix; skipped job behavior
- [GitHub Docs: Running variations of jobs](https://docs.github.com/actions/using-jobs/using-a-matrix-for-your-jobs) — fromJson matrix pattern, dynamic matrices

### Secondary (MEDIUM confidence)
- [GitHub Community #27096](https://github.com/orgs/community/discussions/27096) — empty matrix fromJson crash; boolean guard workaround
- [GitHub Community #45058](https://github.com/orgs/community/discussions/45058) — success() returns false when needed job skipped
- [GitHub Community #45734](https://github.com/orgs/community/discussions/45734) — inputs context unreliable at workflow-level concurrency
- [GitHub Community #152605](https://github.com/orgs/community/discussions/152605) + [#18001](https://github.com/orgs/community/discussions/18001) — skipped jobs cannot be hidden from GHA UI; no planned fix
- [GitHub Community #120093](https://github.com/orgs/community/discussions/120093) — 65,535 char limit confirmed across all workflow_dispatch inputs
- [Digger CE source: github_actions.go](https://github.com/diggerhq/digger/blob/develop/backend/ci_backends/github_actions.go) — per-project dispatch model; no batching (confirms Ferry v1.5 is novel)
- [Atlantis parallel plan/apply #260](https://github.com/runatlantis/atlantis/issues/260) — closest prior art to batched multi-resource dispatch

### Tertiary (LOW confidence)
- [GitHub Community #35341](https://github.com/orgs/community/discussions/35341) — job-level concurrency with `needs` outputs (unverified; not needed for v1.5 which uses hardcoded group names)
- v1.4 research files (ARCHITECTURE.md, PITFALLS.md, FEATURES.md) — patterns and anti-patterns that explicitly informed v1.5 design decisions

---
*Research completed: 2026-03-10*
*Ready for roadmap: yes*
