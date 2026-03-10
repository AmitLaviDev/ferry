# Project Research Summary

**Project:** Ferry v1.4 Unified Workflow Consolidation
**Domain:** GitHub Actions YAML architecture / serverless deploy tooling
**Researched:** 2026-03-10
**Confidence:** HIGH

## Executive Summary

Ferry v1.4 is a targeted refactor: three per-type workflow files (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) are replaced by a single `ferry.yml`. The change is deliberately minimal. The backend still sends one `workflow_dispatch` per resource type — only the target filename changes from a type-derived string to the hardcoded constant `"ferry.yml"`. Inside the unified workflow, a shared `setup` job exposes `resource_type` as a GHA output, and three conditional deploy jobs use `if: needs.setup.outputs.resource_type == '<type>'` to route execution. No new libraries or dependencies are required.

The recommended approach is Option B (backend dispatches to a single file, routing done in YAML via job-level `if` conditions). This is the correct architecture because it preserves the proven per-type dispatch model, keeps GHA logs clean and focused on one type per run, and requires only four small code edits plus the new workflow template. The alternative approaches — reusable workflows, matrix-based routing, or a monolithic dispatch — all add abstraction, indirection, or complexity that this straightforward refactor does not need.

The main risks are operational, not technical. Concurrency misconfiguration (a workflow-level concurrency group would silently cancel parallel type dispatches) and migration ordering (the backend must not be deployed before `ferry.yml` lands in the user's default branch) are the two traps that require deliberate attention. Both have well-documented prevention strategies. All GHA behavioral dependencies (parallel workflow runs, skipped-job semantics, empty-matrix guard) are verified against official GitHub documentation with HIGH confidence.

## Key Findings

### Recommended Stack

No new stack elements are introduced in v1.4. The project continues to use Python 3.14, Pydantic v2 (the `DispatchPayload` model already carries `resource_type`), and the existing composite action infrastructure. The only stack change is in `constants.py`: `RESOURCE_TYPE_WORKFLOW_MAP` (a dict mapping resource type to workflow suffix) is removed and replaced with a single string constant `WORKFLOW_FILENAME = "ferry.yml"`.

**Core technologies:**
- Python 3.14: Backend + action logic — already in use, no change
- Pydantic v2: `DispatchPayload` model — `resource_type` field already present, no schema change
- GitHub Actions: Target execution platform — conditional job routing via `if:` is core GHA functionality

**Full detail:** `.planning/research/STACK.md`

### Expected Features

FEATURES.md was not produced because v1.4 introduces no new user-facing features. This is a pure infrastructure refactor that reduces the number of workflow files users must create from 3 to 1. The feature set delivered is:

**Must have (table stakes for this release):**
- Single `ferry.yml` that replaces all three per-type workflow files — direct ask from v1.4 scope
- Parallel dispatch behavior preserved — lambdas and step functions still deploy simultaneously, not serialized
- Clean GHA UI with distinguishable run names per resource type — `run-name` using `fromJson(inputs.payload).resource_type`

**Deferred (v2+):**
- Deploy locking at the resource level (not workflow level) — relevant for v2 PR integration
- Feature flag in `ferry.yaml` to support gradual per-repo migration — needed when multi-tenant

### Architecture Approach

The unified workflow uses a 4-job structure: one shared `setup` job followed by three independent conditional deploy jobs. The `setup` job parses the dispatch payload and outputs both `matrix` (unchanged from v1.3) and `resource_type` (new). Each deploy job declares `if: needs.setup.outputs.resource_type == '<type>'` and its own job-level concurrency group (`ferry-deploy-<type>`, `cancel-in-progress: false`). When a job's `if` is false, GHA skips the entire job including matrix evaluation — this is the critical guard against the `fromJson` empty-matrix crash.

**Major components and changes:**

| Component | Action | What changes |
|-----------|--------|-------------|
| `constants.py` (ferry-utils) | Modify | Remove `RESOURCE_TYPE_WORKFLOW_MAP`, add `WORKFLOW_FILENAME = "ferry.yml"` |
| `trigger.py` (ferry-backend) | Modify | Use `WORKFLOW_FILENAME` instead of per-type filename derivation (2 lines) |
| `parse_payload.py` (ferry-action) | Modify | Add `set_output("resource_type", payload.resource_type)` (1 line) |
| `setup/action.yml` (ferry-action) | Modify | Expose `resource_type` output (3 lines) |
| `ferry.yml` (user workflow) | New | Single file: setup job + 3 conditional deploy jobs |
| `ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml` | Delete | Replaced by `ferry.yml` |

**Full detail:** `.planning/research/ARCHITECTURE.md`

### Critical Pitfalls

1. **Workflow-level concurrency group cancels parallel dispatches** — When a push touches multiple resource types, the backend fires N dispatches to `ferry.yml`. A shared concurrency group (e.g., `concurrency: group: ${{ github.workflow }}`) causes each new dispatch to cancel the previous one. Prevention: do NOT add workflow-level concurrency. Use job-level concurrency groups keyed by hardcoded type name (`ferry-deploy-lambda`, `ferry-deploy-step-function`, `ferry-deploy-api-gateway`).

2. **Migration order: user repo first, then backend** — If the backend is deployed before `ferry.yml` exists on the user's default branch, all dispatches return 404 silently. The GHA UI shows nothing. Prevention: (1) merge `ferry.yml` to user repo default branch, (2) deploy backend, (3) delete old workflow files.

3. **Empty matrix crash if `if` guard is missing** — `fromJson` on an empty or mismatched matrix produces a GHA runner error. Prevention: the `if` condition on the job must be the gate, not step-level conditions. When `if` is false, GHA never evaluates `strategy.matrix`. Do not put the `if` on steps while leaving the job-level `if` absent.

4. **Indistinguishable run names** — Three simultaneous dispatches to `ferry.yml` all show "Ferry Deploy" in the Actions tab. Prevention: add `run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}"` at the workflow level.

5. **Test suite must be updated atomically** — Existing dispatch tests assert workflow filenames like `ferry-lambdas.yml`. After the backend change, all such assertions must be updated in the same commit. Prevention: search for the old filenames before landing the PR.

**Full detail:** `.planning/research/PITFALLS.md`

## Implications for Roadmap

Based on combined research, the implementation has a natural 3-phase dependency chain. Phases 1a and 1b are independent of each other (can be parallelized), Phase 2 depends on both completing, and Phase 3 is E2E validation.

### Phase 1a: Backend Constant Change

**Rationale:** Self-contained, lowest risk change. Establishes the new dispatch target. Must land with test updates in the same commit to keep CI green.
**Delivers:** Backend now dispatches all resource types to `ferry.yml` (not yet deployed — in progress)
**Implements:** `constants.py` rename + `trigger.py` simplification
**Avoids:** Pitfall 13 (broken tests) by updating test assertions atomically

### Phase 1b: Setup Action Output

**Rationale:** Independent of Phase 1a, can be developed and tested in parallel. Purely additive (one new `set_output` call). Zero risk to the existing `build_matrix()` logic.
**Delivers:** `action/setup` now exposes `resource_type` output alongside `matrix`
**Implements:** `parse_payload.py` + `setup/action.yml` changes
**Avoids:** Pitfall 3 (empty matrix) because `if` on the job gates matrix evaluation

### Phase 2: Unified Workflow Template + Docs

**Rationale:** Depends on Phase 1b completing (the template references `resource_type` output). Create the canonical `ferry.yml` template and update all three docs pages.
**Delivers:** `ferry.yml` workflow file ready for test repo; docs updated
**Uses:** All patterns from STACK.md (no new dependencies)
**Avoids:** Pitfall 1 (no workflow-level concurrency group), Pitfall 4 (using job-level `if` guard), Pitfall 5 (add `run-name` with `fromJson` fallback)

### Phase 3: Test Repo Migration + E2E Validation

**Rationale:** Must happen after both Phase 1 branches and Phase 2 are deployed. Migration order is critical (see Pitfall 4 and 9).
**Delivers:** Test repo (`AmitLaviDev/ferry-test-app`) running on unified `ferry.yml`; old 3 files deleted; E2E confirmed for all three resource types
**Avoids:** Pitfall 9 (deploy user repo before backend) by following documented cutover order

### Phase Ordering Rationale

- Phases 1a/1b are independent because the backend constant change has no dependency on the action output change and vice versa
- Phase 2 is blocked on 1b because `ferry.yml` references `resource_type` output that must exist before it can be written with correct action references
- Phase 3 is the integration gate — both backend (1a) and action (1b) changes must be deployed, and the template (2) finalized, before the test repo is touched
- This order avoids the most dangerous pitfall (Pitfall 4): `ferry.yml` is in the test repo before the backend switches its dispatch target

### Research Flags

Phases with well-documented patterns (no additional research needed):
- **Phase 1a:** Standard Python constant refactor + test update — no ambiguity
- **Phase 1b:** Additive GHA output — `set_output` pattern is identical to existing `matrix` output
- **Phase 2:** Complete `ferry.yml` template is already written in STACK.md (see "Unified ferry.yml Template (Complete)" section)
- **Phase 3:** Migration order is fully specified in Pitfall 4 and 9 prevention strategies

No phases require deeper research before planning. All GHA behavioral questions (parallel dispatches, skipped jobs, concurrency groups, `run-name`) are resolved with HIGH confidence against official documentation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new technologies; changes are removals and simplifications to an already-working system |
| Features | HIGH | Scope is fully specified; FEATURES.md not needed for a no-new-features refactor |
| Architecture | HIGH | All GHA behaviors verified against official docs; code changes are minimal and additive |
| Pitfalls | HIGH | Primary pitfalls (concurrency, migration order, empty matrix) confirmed via official docs + community consensus |

**Overall confidence:** HIGH

### Gaps to Address

- **Multi-tenant migration path:** The current design assumes a single test repo with coordinated cutover. If v2 brings multiple repos, a per-repo `workflow_version` field in `ferry.yaml` (or a feature flag) will be needed to support gradual migration. Not a gap for v1.4 execution, but document the design decision.
- **`has_lambdas` / `has_step_functions` / `has_api_gateways` boolean outputs:** PITFALLS.md (Pitfall 3) recommends dedicated boolean outputs from the setup action in addition to `resource_type`. The ARCHITECTURE.md design uses only `resource_type` for routing. Since the `if` guard at the job level prevents the matrix from being evaluated when `resource_type` doesn't match, the boolean outputs are redundant for v1.4. Resolve explicitly during Phase 1b implementation: use `resource_type` string comparison only (simpler) unless a race condition or edge case surfaces in testing.

## Sources

### Primary (HIGH confidence)
- [GitHub Docs: Control concurrency](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) — concurrency group semantics, cancel-in-progress behavior
- [GitHub Docs: Using conditions for job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) — job-level `if`, skipped job behavior
- [GitHub Docs: Workflow syntax](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) — `run-name`, `workflow_dispatch` inputs, permissions
- [GitHub Docs: Actions limits](https://docs.github.com/en/actions/reference/limits) — concurrent job limits, input size limits
- [GitHub Changelog: Dynamic run names](https://github.blog/changelog/2022-09-26-github-actions-dynamic-names-for-workflow-runs/) — `run-name` feature
- Ferry codebase: `trigger.py`, `constants.py`, `parse_payload.py`, `action/setup/action.yml`, `dispatch.py` — direct code analysis

### Secondary (MEDIUM confidence)
- [Community Discussion #27096: Empty matrix crashes](https://github.com/orgs/community/discussions/27096) — `fromJson` on empty array behavior
- [Community Discussion #45734: inputs context bug in workflow-level concurrency](https://github.com/orgs/community/discussions/45734) — `${{ inputs.X }}` silently ignored at workflow-level concurrency
- [Community Discussion #9252 / #53506: Concurrency cancels parallel dispatches](https://github.com/orgs/community/discussions/9252) — confirmed scenario
- [Community Discussion #45058: success() false when needed job skipped](https://github.com/orgs/community/discussions/45058) — skipped job cascade behavior
- [Community Discussion #60792: Skipped jobs report Success for status checks](https://github.com/orgs/community/discussions/60792) — branch protection compatibility
- Ferry test repo: `AmitLaviDev/ferry-test-app/.github/workflows/ferry-*.yml` — current per-type workflow structure

---
*Research completed: 2026-03-10*
*Ready for roadmap: yes*
