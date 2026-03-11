# Feature Landscape: Unified Workflow Consolidation (v1.4)

**Domain:** GitHub Actions workflow consolidation for serverless deploy tool
**Researched:** 2026-03-10
**Scope:** Consolidating three per-type workflow files into a single `ferry.yml`

## Table Stakes

Features users expect. Missing = the consolidation feels broken or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single `ferry.yml` replaces all three files | The entire point of this milestone; users maintain one file | Low | Rename target in dispatch, update docs |
| Conditional job routing by resource type | Only the matching type's job runs per dispatch | Low | `if: needs.setup.outputs.resource_type == 'lambda'` pattern |
| Parallel dispatch still works (multi-type push) | A push affecting lambdas + SFs must still trigger both; each runs independently | Medium | Two separate dispatches to same `ferry.yml`, must not cancel each other |
| Setup action exposes `resource_type` output | Downstream jobs need to know which type was dispatched to conditionally run | Low | Add output to setup action from `DispatchPayload.resource_type` |
| Existing matrix fan-out preserved per type | Each type still fans out across its affected resources via `strategy.matrix` | Low | No change to matrix logic, just wrapped in conditional jobs |
| Content-hash skip detection still works | Deploy-level skip must still function within the unified workflow | None | No change needed -- happens inside deploy actions |
| Dispatch-level skip still works | Backend still skips dispatch when no resources affected | None | No change needed -- happens in backend before dispatch |
| Updated workflow template in docs | Users need a copy-paste template for the new `ferry.yml` | Low | Replace three doc sections with one unified template |
| Clear job names in GHA UI | Each job must be identifiable: "Ferry: setup", "Ferry: deploy order-processor (lambda)" | Low | Use `name:` field on jobs |
| Old workflow files no longer needed | Docs must explicitly say to delete old files; warn about 404 if old files remain | Low | Migration note in docs |

## Differentiators

Features that make the consolidation feel well-crafted vs. a mechanical merge.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Concurrency groups per resource type | Two dispatches (lambda + SF) run in parallel, but two lambda dispatches from rapid pushes queue properly | Medium | Use job-level concurrency with `ferry-lambdas-${{ github.repository }}` group; see Concurrency Model section |
| Setup outputs `has_lambdas`, `has_step_functions`, `has_api_gateways` booleans | More readable `if:` conditions than string comparison; forward-compatible with future "all-in-one dispatch" | Low | Parse type from payload, set boolean outputs |
| Empty matrix guard | If somehow a type job runs with no resources of that type, prevent crash from empty `fromJson` | Low | `if: needs.setup.outputs.matrix != '[]'` on deploy jobs. GHA crashes on empty matrix vector -- this is a known footgun. |
| Shared setup job (single parse, multiple consumers) | One `setup` job, three conditional deploy jobs that read its outputs -- avoids re-parsing payload per type | Low | Already the pattern in per-type files; extend with type-conditional outputs |
| Workflow-level `name:` with dynamic type | Workflow run shows "Ferry Deploy (lambda)" not just "Ferry Deploy" in GHA UI | Low-Med | `run-name: "Ferry: ${{ github.event.inputs.payload }}"` -- but payload is JSON, need to extract type; may require setup step |
| Explicit `fail-fast: false` on each matrix job | One failing resource doesn't cancel others of same type | None | Already in current templates; preserve it |

## Anti-Features

Features to explicitly NOT build as part of v1.4.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Merging all types into a single dispatch | Would require backend rework (Option A from PROJECT.md), increases payload size, breaks per-type concurrency | Keep per-type dispatch (Option B). Backend sends N dispatches, all target `ferry.yml` |
| Dynamic job generation (generate jobs from payload) | GHA does not support dynamic job creation at runtime; jobs must be statically defined in YAML | Define three static deploy jobs (lambdas, step_functions, api_gateways), skip via `if:` |
| Reusable workflow (`workflow_call`) wrapper | Adds indirection, still need the dispatch file, and reusable workflows have context limitations | Keep everything in a single composite workflow file |
| `run-name` parsing payload JSON | Extracting `resource_type` from JSON in run-name expression is fragile (no `fromJson` in run-name context) | Use static workflow name; type is visible in job names |
| Hiding skipped jobs in GHA UI | GHA has no built-in way to hide skipped jobs (long-standing community request, no fix planned) | Accept skipped jobs appear grayed out; ensure job names make it clear what ran |
| Workflow-level concurrency | `inputs` context does not reliably work at workflow-level concurrency (confirmed GHA bug); would block parallel multi-type dispatches | Use job-level concurrency groups instead, or omit entirely for v1.4 |
| Backward-compatible dual-mode (support both old and new files) | Increases maintenance surface for zero benefit; clean cut is better | Migration guide: delete old files, add new one |
| Adding new resource types in this milestone | v1.4 is about consolidation, not feature expansion | New types (if any) are separate milestones |

## Feature Dependencies

```
Backend: dispatch.py workflow filename change
    |
    v
Setup Action: expose resource_type output
    |
    +---> Unified ferry.yml template (static YAML)
    |         |
    |         +---> Conditional lambda deploy job
    |         +---> Conditional step_functions deploy job
    |         +---> Conditional api_gateways deploy job
    |
    +---> Updated docs (lambdas.md, step-functions.md, api-gateways.md -> unified)
    |
    +---> Test repo: replace 3 files with 1 ferry.yml
    |
    v
Constants: RESOURCE_TYPE_WORKFLOW_MAP update (all types -> "ferry" or remove map)
```

### Dependency Detail

1. **`dispatch.py` (backend)** depends on `constants.py` (`RESOURCE_TYPE_WORKFLOW_MAP`). Currently builds `ferry-{workflow_name}.yml` from the map. Must change to emit `ferry.yml` for all types. Two approaches:
   - Change the map values to all return same string (breaking separation of concerns)
   - Hardcode `workflow_file = "ferry.yml"` and remove/simplify the map

2. **Setup action (`parse_payload.py`)** currently outputs only `matrix`. Must additionally output `resource_type` (string) so the unified workflow's conditional jobs can route. The `DispatchPayload` model already contains `resource_type` -- just needs to be surfaced as a GHA output.

3. **Unified `ferry.yml`** depends on both the above. It is a static YAML file with three conditional deploy job blocks, each gated on the setup output.

4. **Docs** depend on the final `ferry.yml` template shape. Should be updated after template is finalized.

5. **Test repo** depends on the final `ferry.yml` template and backend deploy (to emit `ferry.yml` dispatches).

## Concurrency Model (Critical Design Decision)

### The Problem

Currently, three separate workflow files means three separate workflow runs that cannot interfere with each other. With a single `ferry.yml`, two concurrent dispatches (e.g., lambda + step_function from the same push) target the SAME workflow file.

### GHA Default Behavior

By default, multiple `workflow_dispatch` triggers to the same workflow run concurrently. This is the desired behavior -- both dispatches run in parallel, each with different payloads.

### When Concurrency Matters

If a user pushes twice in quick succession, both pushes may trigger lambda dispatches. Without concurrency control, both run simultaneously, potentially deploying overlapping resources.

### Recommended Approach for v1.4

**Do NOT add workflow-level concurrency.** Reasons:
1. `inputs` context is unreliable at workflow-level concurrency (confirmed GHA bug)
2. A static concurrency group would serialize ALL dispatches, blocking multi-type parallelism
3. The current per-type files have no concurrency control, so this is not a regression

**If concurrency is added later (v2.0)**, use job-level concurrency with resource_type in the group name:
```yaml
jobs:
  deploy-lambdas:
    concurrency:
      group: ferry-lambdas-${{ github.repository }}
      cancel-in-progress: false
```

This is a **differentiator** (nice-to-have), not table stakes for v1.4.

## GHA Conditional Job Patterns (Implementation Guide)

### Pattern: Setup -> Conditional Deploy Jobs

```yaml
jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
      resource_type: ${{ steps.parse.outputs.resource_type }}
    steps:
      - uses: actions/checkout@v4
      - id: parse
        uses: ./action/setup
        with:
          payload: ${{ inputs.payload }}

  deploy-lambdas:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - uses: ./action/build
        # ...
      - uses: ./action/deploy
        # ...

  deploy-step-functions:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'step_function'
    # ...

  deploy-api-gateways:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.resource_type == 'api_gateway'
    # ...
```

### Known GHA Gotchas for This Pattern

1. **Skipped jobs show in UI:** All three deploy jobs appear in the GHA run, two will show "skipped". No way to hide them (confirmed: no GHA feature for this). Mitigation: clear `name:` fields make it obvious which one ran.

2. **Empty matrix crash:** If a job's `if:` condition passes but the matrix is empty, GHA crashes with "Matrix vector does not contain any values". Mitigation: the `if: resource_type == 'X'` guard prevents this because the matrix always has entries when the type matches (setup action only builds matrix for the dispatched type).

3. **Downstream jobs after skipped `needs`:** If a job depends on a skipped job, it is also skipped by default. This does NOT affect v1.4 because there are no downstream jobs after the deploy jobs. But if v2.0 adds a "report" job that `needs: [deploy-lambdas, deploy-step-functions, deploy-api-gateways]`, it would need `if: always() && !failure() && !cancelled()` to avoid being skipped. Flag for v2.0 planning.

4. **`success()` returns false if deps skipped:** Related to above. The implicit `success()` check in `if:` considers skipped deps as not-success. Workaround: `if: always() && !failure() && !cancelled()`.

## Existing Codebase Touchpoints

Files that need modification for v1.4:

| File | Current State | Change Needed |
|------|--------------|---------------|
| `utils/src/ferry_utils/constants.py` | `RESOURCE_TYPE_WORKFLOW_MAP` maps types to `lambdas`, `step_functions`, `api_gateways` | Either remove map usage or update; dispatch.py builds `ferry-{name}.yml` from it |
| `backend/src/ferry_backend/dispatch/trigger.py` | Line 154-155: `workflow_file = f"ferry-{workflow_name}.yml"` | Change to `workflow_file = "ferry.yml"` |
| `action/src/ferry_action/parse_payload.py` | Outputs only `matrix` | Add `set_output("resource_type", payload.resource_type)` |
| `action/setup/action.yml` | Declares only `matrix` output | Add `resource_type` output declaration |
| `docs/lambdas.md` | Documents `ferry-lambdas.yml` | Update to reference unified `ferry.yml` |
| `docs/step-functions.md` | Documents `ferry-step_functions.yml` | Update to reference unified `ferry.yml` |
| `docs/api-gateways.md` | Documents `ferry-api_gateways.yml` | Update to reference unified `ferry.yml` |
| Test repo workflow files | 3 separate files | Replace with single `ferry.yml` |

## MVP Recommendation

Prioritize (in order of implementation):

1. **Setup action: add `resource_type` output** -- Lowest risk, enables everything else. One line in `parse_payload.py`: `set_output("resource_type", payload.resource_type)`. One line in `action.yml` outputs declaration. Add tests.

2. **Constants/dispatch: change workflow filename** -- Change `trigger.py` line 155 to hardcode `ferry.yml` (or simplify `RESOURCE_TYPE_WORKFLOW_MAP`). Small backend change, high impact. Add/update tests.

3. **Unified `ferry.yml` template** -- Static YAML with setup + 3 conditional deploy jobs. This is the artifact users copy into their repo.

4. **Docs update** -- Replace per-type workflow sections in `lambdas.md`, `step-functions.md`, `api-gateways.md` with unified template reference.

5. **Test repo update** -- Delete 3 old workflow files, add `ferry.yml`, push to verify E2E.

Defer:
- **Concurrency groups:** Not needed for v1.4. Current behavior (parallel runs, no concurrency control) is preserved from v1.3. Add in v2.0 if rapid-push race conditions become a problem.
- **`run-name` dynamic naming:** Fragile in GHA, low value. Static "Ferry Deploy" is fine; job names provide the detail.
- **Boolean convenience outputs (`has_lambdas` etc.):** Nice-to-have but `resource_type == 'lambda'` is clear enough. Could add later if moving to single-dispatch model in v2.0.

## Sources

- [GitHub Docs: Using conditions to control job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) -- Skipped job reports "Success" status, `if:` syntax (HIGH confidence)
- [GitHub Docs: Control the concurrency of workflows and jobs](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) -- Concurrency group syntax, `cancel-in-progress` (HIGH confidence)
- [GitHub Community: Job with dynamic matrix crashes if matrix contains zero elements](https://github.com/orgs/community/discussions/27096) -- Empty `fromJson` matrix crash, `if:` guard workaround (MEDIUM confidence)
- [GitHub Community: Hide Skipped jobs from Action UI](https://github.com/orgs/community/discussions/152605) -- No GHA feature to hide skipped jobs (MEDIUM confidence)
- [GitHub Community: Hide Jobs in Actions UI when If is false](https://github.com/orgs/community/discussions/18001) -- Confirmed: skipped jobs always visible (MEDIUM confidence)
- [GitHub Community: inputs context not working for concurrency group](https://github.com/orgs/community/discussions/35341) -- `inputs` unreliable at workflow-level concurrency; use job-level or `github.event.inputs` (MEDIUM confidence)
- [GitHub Community: Jobs being skipped while using both needs and if](https://github.com/orgs/community/discussions/26945) -- `always()` workaround for skipped dependency chains (MEDIUM confidence)
- [GitHub Community: success() returns false if dependent jobs are skipped](https://github.com/orgs/community/discussions/45058) -- Implicit `success()` treats skipped as not-success (MEDIUM confidence)
- [Digger CE Getting Started](https://docs.opentaco.dev/ce/getting-started/with-terraform) -- Reference: single `workflow_dispatch` file for multiple project types (MEDIUM confidence)
- Existing Ferry codebase: `dispatch/trigger.py`, `parse_payload.py`, `constants.py`, dispatch models, per-type workflow docs (PRIMARY source)
