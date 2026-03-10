# Feature Landscape: Batched Dispatch (v1.5)

**Domain:** GitHub Actions dispatch consolidation for multi-type serverless deploy tool
**Researched:** 2026-03-10
**Scope:** Replacing per-type `workflow_dispatch` with a single batched dispatch per push

## Table Stakes

Features users expect from batched dispatch. Missing = the feature feels broken or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single dispatch per push | The entire point of v1.5; one push = one workflow run regardless of how many types changed | Medium | Backend must batch all affected types into one payload, fire one `workflow_dispatch` |
| All affected types deploy in one run | A push touching lambdas + SFs + APGW results in one workflow run with all three deploying | Medium | Setup action must parse batched payload and output per-type matrices |
| Only relevant deploy jobs run (no skipped-job noise) | The v1.4 pain point: 2 skipped jobs per run. Batched dispatch must eliminate or reduce this | Medium-High | Requires setup action to output boolean flags (`has_lambdas`, `has_step_functions`, `has_api_gateways`) and jobs to use `if:` guards with empty-matrix protection |
| Per-type matrix fan-out preserved | Lambdas still fan out in parallel via matrix; SF and APGW still use their own strategies | Low | Each deploy job gets its own matrix output from setup; no change to matrix shape |
| Content-hash skip detection still works | Deploy-level skip for unchanged content must still function | None | No change needed -- happens inside deploy actions |
| Payload schema backward-compatible or cleanly versioned | Breaking the dispatch contract between App and Action must be handled explicitly | Low | Bump `SCHEMA_VERSION` to 2; setup action can detect version and handle both during rollout |
| Dynamic `run-name` shows all affected types | User sees "Ferry Deploy: lambda, step_function" not generic "Ferry Deploy" | Low | `run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_types || 'manual' }}"` -- `fromJson` works in `run-name` context (HIGH confidence, already used in v1.4 template) |
| Concurrency groups still prevent overlapping deploys of same type | Two rapid pushes both affecting lambdas must not deploy concurrently | Low | Job-level concurrency groups already in v1.4 template; preserved as-is |
| Payload fits within GHA 65,535 character limit | Batched payload combining multiple types must not exceed the single-input size limit | Low | Current per-type payloads are small (a few KB). Even batching 3 types with 10+ resources each stays well under 65K. Existing `_MAX_PAYLOAD_SIZE` check in `trigger.py` still applies to the combined payload |

## Differentiators

Features that make batched dispatch feel polished vs. a mechanical merge.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Clean GHA UI: only active jobs visible | When only lambdas change, user sees `setup` + `deploy-lambda` jobs only, no grayed-out SF/APGW jobs | High | GHA has NO built-in way to hide skipped jobs (confirmed: no feature planned). The ONLY way to avoid skipped jobs appearing is to not define them in the workflow. This means either: (a) accept skipped jobs (current v1.4 behavior), or (b) use a fundamentally different workflow structure (see Architecture section). Option (b) is the differentiator but requires significant workflow redesign |
| Ordered deploy across types | Deploy APGW after SF after Lambda when all three change in one push (respects dependency chain) | Medium | Use `needs:` between deploy jobs. Currently all types deploy independently; adding ordering is new behavior. Requires defining a dependency graph (lambda first, then SF, then APGW). Only relevant when multiple types present |
| Single setup parse, multiple consumers | Setup job parses payload once, outputs N matrices -- downstream jobs each consume their own | Low | Already the pattern. Setup outputs `lambda_matrix`, `sf_matrix`, `apgw_matrix` instead of single `matrix`. Cleaner than v1.4 where setup only outputs one matrix because only one type is present |
| Aggregated status reporting | One PR Check Run summary covering all types deployed in this push, not N separate statuses | Medium | Currently each deploy job posts its own Check Run. A summary job at the end could aggregate results. Requires a new `report` job with `if: always()` pattern |
| Dispatch deduplication within batch | If a push somehow triggers the webhook twice (rare but possible), the batched dispatch deduplicates at the batch level not per-type | None | Already handled by DynamoDB dedup -- one webhook = one dedup key. Batching doesn't change this |
| Graceful degradation for oversized payloads | If the combined payload exceeds 65K (extreme edge case), fall back to per-type dispatch | Medium | Backend checks combined size, splits into per-type dispatches if too large. Preserves v1.4 behavior as fallback |

## Anti-Features

Features to explicitly NOT build as part of v1.5.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Dynamic job generation at runtime | GHA does not support creating jobs dynamically -- all jobs must be statically defined in YAML. You cannot say "for each type in payload, create a deploy job" | Define 3 static deploy jobs (lambda, SF, APGW), each with `if:` guards based on setup outputs. This is a fundamental GHA limitation, not a design choice |
| Single mega-matrix across all types | Putting lambdas, SFs, and APGW resources into one matrix would require each matrix entry to carry different fields depending on type, and each step would need type-conditional logic | Keep separate matrices per type. Each deploy job knows its type and has type-specific steps. Clean separation |
| Reusable workflows (`workflow_call`) per type | Adds indirection (3 extra files), reusable workflows have context limitations (`secrets` access differs, `GITHUB_TOKEN` scoping), and the user must maintain 4 files instead of 1 | Keep everything in single `ferry.yml`. The whole point of v1.4 was consolidation |
| Removing `if:` guards entirely | Cannot be done while having static deploy jobs. GHA evaluates all defined jobs and marks unused ones as skipped | Accept that skipped jobs show in GHA UI when not all types are affected. Use clear `name:` fields so it's obvious which ran. The alternative (not defining the jobs) breaks the workflow for pushes that DO affect those types |
| Per-resource dispatch (one dispatch per changed resource) | Explodes the number of workflow runs. A push changing 5 lambdas + 2 SFs = 7 dispatches vs. 1 batched dispatch. Terrible UX, wasteful runner time | Batch by push event, fan out by type via matrices |
| Waiting for GHA to add "hide skipped jobs" feature | Feature has been requested since 2021 with no indication of implementation (GitHub Community discussions #18001, #152605). Building around this limitation is more productive | Design clear job names, accept grayed-out jobs, document expected behavior |
| Cross-type rollback in batch | If lambda deploys succeed but SF fails, do NOT roll back lambdas. Cross-resource rollback is unsolved for serverless and explicitly out of scope | Each type deploys independently. Failures are reported per-resource. User fixes and re-pushes |
| Supporting multiple dispatch inputs | GHA allows up to 25 inputs for `workflow_dispatch`, but using a single `payload` JSON input is cleaner than splitting into `lambda_payload`, `sf_payload`, `apgw_payload` | Keep single `payload` input containing all types. Parse in setup action |

## Feature Dependencies

```
Backend: trigger.py batches all types into single DispatchPayload v2
    |
    v
Shared: DispatchPayload model v2 (supports multiple resource types)
    |
    v
Setup Action: parse_payload.py outputs per-type matrices + boolean flags
    |
    +---> Updated ferry.yml template
    |         |
    |         +---> deploy-lambda job (if: has_lambdas)
    |         +---> deploy-step-function job (if: has_step_functions)
    |         +---> deploy-api-gateway job (if: has_api_gateways)
    |
    +---> Updated docs (setup.md workflow template section)
    |
    +---> Test repo: update ferry.yml, push multi-type change, verify single run
    |
    v
Constants: SCHEMA_VERSION bump (1 -> 2)
```

### Dependency Detail

1. **Payload model (`dispatch.py`)**: Currently `DispatchPayload` has a single `resource_type: str` and `resources: list[Resource]` where all resources are the same type. The batched model needs either:
   - **Option A (recommended)**: Change to `resource_types: list[str]` and keep `resources: list[Resource]` as a mixed-type list. The discriminated union already handles type routing via `resource_type` field on each Resource model. This is the minimal schema change.
   - **Option B**: Nest by type: `lambdas: list[LambdaResource]`, `step_functions: list[StepFunctionResource]`, `api_gateways: list[ApiGatewayResource]`. Cleaner but larger schema change.

2. **Backend (`trigger.py`)**: Currently loops over `grouped` dict and fires one dispatch per type. Must change to: build one combined payload with all types, fire one dispatch. The `_build_resource` function already handles all types -- just needs to be called for all groups and combined.

3. **Setup action (`parse_payload.py`)**: Currently calls one builder based on `payload.resource_type`. Must change to: iterate all resource types present, call each builder, output separate matrices. New outputs: `lambda_matrix`, `sf_matrix`, `apgw_matrix`, `has_lambdas`, `has_step_functions`, `has_api_gateways`.

4. **Workflow template (`ferry.yml`)**: Jobs change from `if: needs.setup.outputs.resource_type == 'lambda'` to `if: needs.setup.outputs.has_lambdas == 'true'`. Each job references its type-specific matrix: `matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}`.

5. **Empty matrix guard**: When `has_lambdas` is false, the lambda job skips via `if:`. But if somehow the guard fails and the job runs with an empty matrix, GHA crashes. The `if:` guard is the primary protection. Secondary: setup action outputs `{"include":[]}` for inactive types, and the job's `if:` prevents evaluation. This is safe because GHA evaluates `if:` BEFORE `strategy.matrix` (HIGH confidence -- confirmed by GHA docs: "You can use the if conditional to prevent a job from running unless a condition is met").

6. **Schema versioning**: Bump `SCHEMA_VERSION` to 2. The setup action should check `v` field and handle v1 payloads (single type) as a migration path during rollout. This allows the backend and action to be deployed independently without coordination.

## Comparison: Per-Type Dispatch (v1.4) vs. Batched Dispatch (v1.5)

| Aspect | Per-Type (v1.4 current) | Batched (v1.5 target) |
|--------|------------------------|----------------------|
| Workflow runs per push | 1 per affected type (up to 3) | Always 1 |
| Skipped jobs per run | 2 (the non-matching types) | 0-2 (types not affected still show as skipped) |
| GHA UI clarity | Cluttered: 3 runs for a full-stack push, each with 2 grayed-out jobs | Cleaner: 1 run, but 0-2 grayed-out jobs remain when not all types affected |
| Backend dispatches | N (one per type) | 1 (combined) |
| Payload schema | Simple: one type per payload | Richer: multiple types per payload |
| Concurrency risk | Low: each type has own run | Medium: one run deploys multiple types, job-level concurrency groups still protect per-type |
| Failure isolation | Natural: each type in its own run | Good: jobs are independent within the run. One type failing does not cancel others (`fail-fast: false` on matrix, no cross-job dependency by default) |
| Run-name readability | "Ferry Deploy: lambda" (clear) | "Ferry Deploy: lambda, step_function" (clear, lists all types) |

### The Skipped-Job Reality

The v1.5 batched dispatch REDUCES but does NOT ELIMINATE skipped-job visual clutter:

- **v1.4**: Push affects lambdas only -> 1 run, 2 skipped jobs (SF, APGW). **Same** push with all 3 types -> 3 runs, each with 2 skipped jobs = 6 skipped jobs total.
- **v1.5**: Push affects lambdas only -> 1 run, 2 skipped jobs (SF, APGW). **Same** push with all 3 types -> 1 run, 0 skipped jobs.

The win is most visible when multiple types change: 3 runs with 6 skipped jobs collapses to 1 run with 0 skipped jobs. For single-type pushes, the visual noise is identical.

## Industry Comparison

### Digger/OpenTaco (direct competitor model)
- **Dispatch model**: One `workflow_dispatch` per project per operation (plan or apply). NOT batched.
- **Payload**: Each dispatch carries a full `Spec` JSON with one Job containing one project.
- **Concurrency**: Backend orchestrates ordering; `max_concurrency_per_batch` controls parallelism.
- **Multiple projects**: Each gets its own GHA workflow run. Concurrency and ordering managed server-side.
- **Implication for Ferry**: Digger chose per-project dispatch. Ferry's v1.4 per-type dispatch is already more efficient (N types << N resources). Batching to single dispatch goes further.

### Atlantis (Terraform, non-GHA)
- **Dispatch model**: Atlantis runs its own server; no GHA dispatch. Processes all affected projects from a single PR event.
- **Parallel execution**: `parallel_plan: true` / `parallel_apply: true` runs projects concurrently within Atlantis server.
- **Locking**: Per-directory+workspace locks allow parallel operations on different projects.
- **Implication for Ferry**: Atlantis's model is closest to batched -- one event triggers processing of all affected resources. Ferry's batched dispatch replicates this within GHA constraints.

### Terraform Cloud/Spacelift
- **Dispatch model**: Workspace-per-resource. Each workspace triggered independently by VCS webhooks.
- **Batching**: No batching -- each workspace runs independently.
- **Implication for Ferry**: No precedent for batching here; these tools embrace per-resource isolation.

### Summary
No direct competitor batches multiple heterogeneous deploy types into a single GHA workflow run. Ferry's batched dispatch would be novel in this space. The pattern is sound (setup job + conditional matrix jobs is well-documented in GHA ecosystem) but there is no prior art to copy from.

## GHA Behavioral Claims (Verified)

| Claim | Status | Source | Confidence |
|-------|--------|--------|------------|
| `fromJson` works in `run-name` context | Verified | Already used in v1.4 ferry.yml template; GitHub docs confirm `inputs` context available in `run-name` | HIGH |
| Empty matrix crashes GHA with "Matrix vector does not contain any values" | Verified | GitHub Community Discussion #27096; multiple confirmations | HIGH |
| `if:` on a job is evaluated BEFORE `strategy.matrix` | Verified | GitHub docs: "You can use the if conditional to prevent a job from running unless a condition is met" -- skipped jobs never evaluate matrix | HIGH |
| Skipped jobs cannot be hidden from GHA UI | Verified | GitHub Community Discussions #18001, #152605; no planned fix | HIGH |
| `inputs` context works at workflow-level concurrency for `workflow_dispatch` | UNRELIABLE | GitHub Community Discussion #35341, #45734; use `github.event.inputs` or job-level concurrency instead | HIGH (that it is unreliable) |
| Maximum payload for `workflow_dispatch` inputs: 65,535 characters | Verified | GitHub docs (workflow syntax) | HIGH |
| Maximum 25 inputs for `workflow_dispatch` | Verified | GitHub docs (workflow syntax) | HIGH |
| `success()` returns false if dependency was skipped | Verified | GitHub Community Discussion #45058; use `if: always() && !failure() && !cancelled()` for downstream jobs after conditional deps | HIGH |
| Job-level concurrency groups can use `needs` outputs | Not verified | No explicit docs found; likely works since job-level expressions have access to `needs` context. Flag for testing | LOW |
| Multiple `workflow_dispatch` to same workflow file run concurrently by default | Verified | Default GHA behavior; no concurrency group = parallel runs | HIGH |

## MVP Recommendation

Prioritize (in order of implementation):

1. **Payload model v2** -- Add support for multiple resource types in `DispatchPayload`. Minimal schema: rename `resource_type` to `resource_types: list[str]`, keep `resources: list[Resource]` as mixed-type discriminated union list. Bump `SCHEMA_VERSION` to 2. Add tests.

2. **Backend: batch into single dispatch** -- `trigger.py` combines all affected types into one payload, fires one `workflow_dispatch`. The loop over `grouped.items()` becomes "build one payload with all resources, dispatch once." Add fallback: if combined payload exceeds 65K, fall back to per-type dispatch (preserves v1.4 behavior). Add tests.

3. **Setup action: multi-type output** -- `parse_payload.py` detects v2 payload, outputs `lambda_matrix`, `sf_matrix`, `apgw_matrix` JSON strings and `has_lambdas`, `has_step_functions`, `has_api_gateways` boolean outputs. Handle v1 payloads for backward compatibility during rollout. Add tests.

4. **Updated ferry.yml template** -- Change `if:` guards from `resource_type == 'lambda'` to `has_lambdas == 'true'`. Change matrix references from `needs.setup.outputs.matrix` to `needs.setup.outputs.lambda_matrix`. Update `run-name` to show all affected types.

5. **Docs update** -- Update setup.md workflow template section with new ferry.yml.

6. **Test repo: multi-type push** -- Push a change touching all 3 types. Verify: single workflow run, all 3 deploy jobs active, correct resources per type, correct run-name.

Defer:
- **Ordered cross-type deploys**: Not needed for v1.5. Types deploy independently. Add dependency ordering in v2.0 if needed.
- **Aggregated status reporting**: A summary job would be nice but is not core to batching. Defer to v2.0.
- **Eliminating skipped-job UI noise entirely**: Not possible with GHA's static job model. Accept 0-2 skipped jobs when not all types change. The major UX win (3 runs -> 1 run) is delivered without solving this.

## Sources

- [GitHub Docs: Running variations of jobs in a workflow (matrix strategy)](https://docs.github.com/actions/using-jobs/using-a-matrix-for-your-jobs) -- Matrix fromJson pattern, dynamic matrices (HIGH confidence)
- [GitHub Docs: Workflow syntax for GitHub Actions](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) -- `run-name` expressions, `workflow_dispatch` input limits (65,535 chars, 25 inputs), `if:` conditional syntax (HIGH confidence)
- [GitHub Docs: Control the concurrency of workflows and jobs](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) -- Concurrency group syntax, job-level vs workflow-level (HIGH confidence)
- [GitHub Docs: Using conditions to control job execution](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/using-conditions-to-control-job-execution) -- `if:` evaluated before matrix; skipped job behavior (HIGH confidence)
- [GitHub Community: Job with dynamic matrix crashes if matrix contains zero elements (#27096)](https://github.com/orgs/community/discussions/27096) -- Empty `fromJson` matrix crash, workarounds (HIGH confidence)
- [GitHub Community: Hide Skipped jobs from Action UI (#152605)](https://github.com/orgs/community/discussions/152605) -- No GHA feature to hide skipped jobs (HIGH confidence)
- [GitHub Community: Hide Jobs in Actions UI when If is false (#18001)](https://github.com/orgs/community/discussions/18001) -- Confirmed: skipped jobs always visible, no planned fix (HIGH confidence)
- [GitHub Community: inputs context not working for concurrency group (#35341)](https://github.com/orgs/community/discussions/35341) -- `inputs` unreliable at workflow-level concurrency (HIGH confidence)
- [GitHub Community: Workflow level concurrency ignores inputs variables (#45734)](https://github.com/orgs/community/discussions/45734) -- Use `github.event.inputs` at workflow level (HIGH confidence)
- [GitHub Community: success() returns false if dependent jobs are skipped (#45058)](https://github.com/orgs/community/discussions/45058) -- Implicit `success()` treats skipped as not-success (HIGH confidence)
- [GitHub Community: workflow_dispatch inputs - max length, number of inputs (#120093)](https://github.com/orgs/community/discussions/120093) -- 65,535 total, 25 max inputs (HIGH confidence)
- [Advanced Usage of GitHub Actions Matrix Strategy (devopsdirective, 2025)](https://devopsdirective.com/posts/2025/08/advanced-github-actions-matrix/) -- Dynamic matrix patterns, multi-job fan-out (MEDIUM confidence)
- [Digger CE source code: `ci_backends/github_actions.go`](https://github.com/diggerhq/digger/blob/develop/backend/ci_backends/github_actions.go) -- One dispatch per project per operation; no batching (HIGH confidence, read source)
- [Digger CE source code: `libs/spec/models.go`](https://github.com/diggerhq/digger/blob/develop/libs/spec/models.go) -- Spec carries single Job; confirms per-project dispatch (HIGH confidence, read source)
- [Atlantis: Run plan/apply for multiple projects in parallel (#260)](https://github.com/runatlantis/atlantis/issues/260) -- `parallel_plan`/`parallel_apply` for concurrent project execution (MEDIUM confidence)
- [Atlantis: Locking and Concurrency Control](https://deepwiki.com/runatlantis/atlantis/5.1-locking-and-concurrency-control) -- Per-directory+workspace locks (MEDIUM confidence)
- Existing Ferry codebase: `trigger.py`, `parse_payload.py`, `constants.py`, `dispatch.py` models, `setup.md` (PRIMARY source)
