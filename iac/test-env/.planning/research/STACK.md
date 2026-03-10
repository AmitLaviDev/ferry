# Technology Stack: v1.4 Unified Workflow

**Project:** Ferry v1.4 Unified Workflow Consolidation
**Researched:** 2026-03-10
**Scope:** GHA YAML patterns for consolidating three per-type workflow files into one `ferry.yml`

## Executive Summary

The unified workflow consolidation requires **zero new libraries or dependencies**. This is purely a GHA YAML architecture change plus a one-line backend change (workflow filename). The core patterns needed are: conditional job execution via `if: needs.setup.outputs.<flag>`, job-level concurrency groups keyed by resource type, and the existing `fromJson` matrix strategy already proven in the per-type workflows. The setup action needs one new output (`resource_type`) alongside the existing `matrix` output.

## What Changes (Minimal)

### Backend Change (1 line)

| Component | Current | New | Why |
|-----------|---------|-----|-----|
| `trigger.py` workflow filename | `f"ferry-{workflow_name}.yml"` | `"ferry.yml"` (hardcoded) | All types dispatch to same file |
| `RESOURCE_TYPE_WORKFLOW_MAP` | Used for filename derivation | **Remove or repurpose** | No longer needed for dispatch routing |

The backend still sends one `workflow_dispatch` per resource type -- that model is preserved. Only the target filename changes.

**Confidence:** HIGH -- direct reading of `trigger.py` line 155.

### Setup Action Change (1 new output)

| Output | Current | New | Why |
|--------|---------|-----|-----|
| `matrix` | JSON matrix for `fromJson()` | **Unchanged** | Still drives per-resource fan-out |
| `resource_type` | Does not exist | **New output** from `parse_payload.py` | Conditional job routing in unified workflow |

The `resource_type` is already in the `DispatchPayload` model (`payload.resource_type`). The `parse_payload.py` just needs to emit it as a second `GITHUB_OUTPUT`.

**Confidence:** HIGH -- `DispatchPayload.resource_type` field confirmed in `dispatch.py` model.

### User Workflow File (the main deliverable)

Replace three files with one `ferry.yml`. Pattern detailed below.

## GHA Patterns Required

### Pattern 1: Conditional Job Execution via Setup Outputs

**What:** A shared `setup` job parses the payload and outputs `resource_type`. Downstream type-specific jobs use `if:` to run only when their type matches.

**Why this pattern:** The backend sends one `workflow_dispatch` per type. Each dispatch triggers the same `ferry.yml`, but only the matching job should execute. The `if:` condition on each job is the cleanest way to achieve this -- no matrix tricks, no reusable workflows, no wrapper scripts.

**Verified behavior:** When a job's `if:` evaluates to false, the job is **skipped** (shows as grey in the UI, not failed). Downstream jobs that `needs:` a skipped job can still run if they use `if: always()` or check `needs.X.result == 'skipped'`. For Ferry, skipped type jobs have no downstream dependents, so this is a non-issue.

```yaml
jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
      resource_type: ${{ steps.parse.outputs.resource_type }}
    steps:
      - uses: actions/checkout@v4
      - name: Parse Ferry payload
        id: parse
        uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambdas:
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      # ... build + deploy Lambda steps

  deploy-step-functions:
    needs: setup
    if: needs.setup.outputs.resource_type == 'step_function'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      # ... deploy Step Functions steps

  deploy-api-gateways:
    needs: setup
    if: needs.setup.outputs.resource_type == 'api_gateway'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      # ... deploy API Gateway steps
```

**Confidence:** HIGH -- `needs.X.outputs.Y` conditional job execution is core GHA functionality, verified in GitHub Docs and multiple community examples.

**Critical note on `fromJson` with empty matrix:** If a job's `if:` condition is false, GHA skips it entirely -- the `strategy.matrix` expression is **never evaluated**. This means the `fromJson` call on the matrix only happens for the job whose type matches. No empty-array crash risk because the non-matching jobs never reach matrix evaluation.

### Pattern 2: Job-Level Concurrency Groups Keyed by Resource Type

**What:** Each type-specific job uses a concurrency group that includes the resource type from the dispatch input, ensuring that concurrent dispatches for different types run in parallel but same-type dispatches are serialized.

**Why this pattern:** When a push changes both Lambdas and Step Functions, the backend fires two `workflow_dispatch` events to `ferry.yml`. Without concurrency groups, both run fully in parallel (which is fine). But if a second push arrives while the first is still deploying Lambdas, you want the second Lambda deploy to queue -- not cancel or collide with the first. Concurrency groups per type solve this.

```yaml
  deploy-lambdas:
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    concurrency:
      group: ferry-deploy-lambda
      cancel-in-progress: false
    # ...
```

**Why `cancel-in-progress: false`:** Deployments should never be interrupted mid-flight. A queued deploy waits for the in-progress one to finish. At most one running + one pending per type.

**Confidence:** HIGH -- verified in GitHub Docs: "there can be at most one running and one pending job in a concurrency group at any time."

**WARNING -- `inputs` context bug at workflow level:** Using `${{ inputs.X }}` in **workflow-level** `concurrency:` blocks is broken for `workflow_dispatch` -- the inputs are silently ignored, causing all runs to share one group. This is a known unresolved bug (GitHub community discussion #45734). **Workaround:** Either use `${{ github.event.inputs.X }}` at workflow level, or (recommended) put concurrency at the **job level** where `inputs` context works correctly. Since Ferry uses job-level concurrency with hardcoded type names (not dynamic input values), this bug does not affect us.

### Pattern 3: Multiple Concurrent Runs of Same Workflow File

**What:** Two `workflow_dispatch` events to `ferry.yml` (one for lambdas, one for step_functions) trigger two independent workflow runs that execute in parallel.

**Why this matters:** The current per-type model works because each type has its own workflow file, so dispatches are inherently parallel. With a unified file, we need confirmation that multiple dispatches to the same file run concurrently.

**Verified behavior:** "GitHub Actions allows multiple workflow runs within the same repository to run concurrently" (GitHub Docs, Concurrency page). Without a shared concurrency group, multiple runs of `ferry.yml` execute in parallel. With per-type concurrency groups at the job level, different types run in parallel and same types serialize. This is exactly the behavior we want.

**Confidence:** HIGH -- directly from GitHub official documentation.

### Pattern 4: Workflow-Level Permissions (Unchanged)

The unified workflow needs the same permissions as each individual workflow:

```yaml
permissions:
  id-token: write    # OIDC JWT for AWS authentication
  contents: read     # Repository checkout
  checks: write      # Check Run status reporting
```

These are set once at the workflow level and apply to all jobs. No change from current pattern.

**Confidence:** HIGH -- same permissions already proven in three existing workflows.

## What NOT to Add

### Do NOT use workflow_call / reusable workflows

**Why avoid:** Reusable workflows add indirection (caller workflow + called workflow), require explicit input/output declarations at the workflow boundary, and have restrictions on `secrets` access. Ferry's jobs are simple enough that inline jobs in one file are clearer than a chain of reusable workflows. The consolidation goal is fewer files, not more abstraction layers.

### Do NOT use matrix to route types

**Why avoid:** You might think: "put all three types in one matrix and use `if:` on steps." This creates a single job that spins up 3 runners where 2 immediately skip all steps. Wasteful. It also makes the GHA UI confusing -- you see matrix entries for types that did nothing. Three explicit jobs with `if:` at the job level is cleaner: only the matching job runs, the others show as "skipped" in grey.

### Do NOT use `continue-on-error` for type routing

**Why avoid:** Using `continue-on-error: true` to let mismatched matrix entries "fail silently" masks real deployment errors. The `if:` condition on the job is the correct mechanism.

### Do NOT add workflow-level concurrency group

**Why avoid:** A single workflow-level concurrency group would serialize ALL dispatches -- a Lambda deploy would block a Step Functions deploy. This defeats the parallel-per-type model. Concurrency must be at the job level, per type.

### Do NOT parse resource_type from the raw input JSON in YAML

**Why avoid:** You might try `if: fromJson(inputs.payload).resource_type == 'lambda'` directly in the workflow YAML. GHA expressions have limited JSON navigation capabilities and this creates fragile coupling between the YAML and the payload schema. Let the setup action (Python) do the parsing and emit a clean string output. Single responsibility.

### Do NOT use `environment` protection rules for type routing

**Why avoid:** GHA environments with required reviewers/wait timers are for deployment approvals, not conditional logic. Using them for type routing would add manual approval steps where none are needed.

## Recommended Stack (No New Dependencies)

### Core Framework (Unchanged)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.14 | Backend + action logic | Already in use, no change |
| Pydantic v2 | latest | Dispatch payload models | Already in use, `resource_type` field exists |
| GitHub Actions | N/A | CI/CD execution | Target platform, no change |

### Backend Changes
| Component | Change | Purpose | Why |
|-----------|--------|---------|-----|
| `trigger.py` | Hardcode `"ferry.yml"` | Single dispatch target | Replace per-type filename derivation |
| `constants.py` | Remove/deprecate `RESOURCE_TYPE_WORKFLOW_MAP` | Dead code cleanup | No longer used for filename |

### Action Changes
| Component | Change | Purpose | Why |
|-----------|--------|---------|-----|
| `action/setup/action.yml` | Add `resource_type` output | Expose type for conditional routing | Workflow jobs need this for `if:` |
| `parse_payload.py` | Emit `resource_type` to `GITHUB_OUTPUT` | Provide the output value | 1-line addition |

### User Workflow Changes
| Component | Change | Purpose | Why |
|-----------|--------|---------|-----|
| `ferry.yml` | New single workflow file | Replace 3 per-type files | Core deliverable |
| `ferry-lambdas.yml` | Delete | Superseded by `ferry.yml` | Consolidation |
| `ferry-step_functions.yml` | Delete | Superseded by `ferry.yml` | Consolidation |
| `ferry-api_gateways.yml` | Delete | Superseded by `ferry.yml` | Consolidation |

### Supporting Libraries (No Changes)
No new libraries needed. The existing stack handles everything:
- `parse_payload.py` already imports `DispatchPayload` which has `resource_type`
- `set_output()` from `ferry_action.gha` already handles `GITHUB_OUTPUT` writing
- No new GHA actions needed beyond what is already used

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Type routing | `if:` on job + setup output | Matrix with step-level `if:` | Wasteful runners, confusing UI |
| Type routing | `if:` on job + setup output | Reusable workflows per type | More files, more indirection -- opposite of goal |
| Concurrency | Job-level per-type groups | Workflow-level concurrency | Serializes all types, breaks parallelism |
| Concurrency | Job-level per-type groups | No concurrency groups | Same-type deploys could collide |
| Payload parsing | Setup action output | Raw `fromJson` in YAML `if:` | Fragile, limited GHA expression capability |
| Workflow structure | One file, 4 jobs (setup + 3 types) | Separate "router" workflow + reusable per-type workflows | Adds complexity, no benefit |

## Installation

No new packages to install. Backend and action changes are modifications to existing files.

```bash
# No new dependencies -- existing stack covers everything
# Changes are to:
#   backend/src/ferry_backend/dispatch/trigger.py  (1 line)
#   utils/src/ferry_utils/constants.py             (cleanup)
#   action/setup/action.yml                        (1 new output)
#   action/src/ferry_action/parse_payload.py       (1 new set_output call)
```

## Unified ferry.yml Template (Complete)

This is the target workflow file that replaces all three per-type files:

```yaml
# .github/workflows/ferry.yml
# Ferry unified deployment workflow
# Triggered by Ferry App via workflow_dispatch for any resource type

name: Ferry Deploy

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"
        required: true

permissions:
  id-token: write    # OIDC JWT for AWS authentication
  contents: read     # Repository checkout
  checks: write      # Check Run status reporting

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
      resource_type: ${{ steps.parse.outputs.resource_type }}
    steps:
      - uses: actions/checkout@v4

      - name: Parse Ferry payload
        id: parse
        uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambdas:
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-lambda
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - name: Build container
        id: build
        uses: AmitLaviDev/ferry/action/build@main
        with:
          resource-name: ${{ matrix.name }}
          source-dir: ${{ matrix.source }}
          ecr-repo: ${{ matrix.ecr }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          runtime: ${{ matrix.runtime }}

      - name: Deploy Lambda
        uses: AmitLaviDev/ferry/action/deploy@main
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          image-uri: ${{ steps.build.outputs.image-uri }}
          image-digest: ${{ steps.build.outputs.image-digest }}
          deployment-tag: ${{ matrix.deployment_tag }}
          trigger-sha: ${{ matrix.trigger_sha }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}

  deploy-step-functions:
    needs: setup
    if: needs.setup.outputs.resource_type == 'step_function'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-step-function
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - name: Deploy Step Functions
        uses: AmitLaviDev/ferry/action/deploy-stepfunctions@main
        with:
          resource-name: ${{ matrix.name }}
          state-machine-name: ${{ matrix.state_machine_name }}
          definition-file: ${{ matrix.definition_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}

  deploy-api-gateways:
    needs: setup
    if: needs.setup.outputs.resource_type == 'api_gateway'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-api-gateway
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - name: Deploy API Gateway
        uses: AmitLaviDev/ferry/action/deploy-apigw@main
        with:
          resource-name: ${{ matrix.name }}
          rest-api-id: ${{ matrix.rest_api_id }}
          stage-name: ${{ matrix.stage_name }}
          spec-file: ${{ matrix.spec_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}
```

## GHA Limitations and Edge Cases

### Empty Matrix Safety
When a job's `if:` evaluates to false, GHA skips the entire job without evaluating `strategy.matrix`. This means `fromJson` on the matrix output is never called for non-matching types. **No risk of "empty matrix" errors.** This was verified through the community discussion on empty matrix handling (Discussion #27096).

### Skipped Job UI Appearance
Skipped jobs appear as grey/dimmed in the GHA Actions tab with "This job was skipped" annotation. This is clean UX -- the user sees which type deployed and which types were not applicable for this dispatch.

### Concurrent Dispatch Race Condition
If the backend fires two dispatches (lambda + step_function) near-simultaneously, both hit `ferry.yml`. Each triggers a separate workflow run. The setup job in each run parses its own payload independently. No shared state, no race condition. **This is the same isolation model as the current per-file approach.**

### Workflow Run Limits
GitHub allows multiple concurrent workflow runs per repository by default (up to plan limits: 20-500 concurrent jobs depending on plan). Two or three concurrent Ferry dispatches are well within limits.

### `inputs` Context at Workflow Level (Known Bug)
`${{ inputs.X }}` is silently ignored in workflow-level `concurrency:` blocks for `workflow_dispatch` (GitHub community discussion #45734). Ferry avoids this by using job-level concurrency with hardcoded group names. If dynamic groups were needed in the future, use `${{ github.event.inputs.X }}` at workflow level instead.

## Sources

- [GitHub Docs: Control concurrency of workflows and jobs](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs) -- HIGH confidence
- [GitHub Docs: Concurrency concepts](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) -- HIGH confidence
- [GitHub Docs: Actions limits](https://docs.github.com/en/actions/reference/limits) -- HIGH confidence
- [GitHub Docs: Workflow syntax](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) -- HIGH confidence
- [GitHub Docs: Using conditions to control job execution](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution) -- HIGH confidence
- [GitHub Community Discussion #27096: Empty matrix crashes](https://github.com/orgs/community/discussions/27096) -- MEDIUM confidence (community, not official docs)
- [GitHub Community Discussion #45734: inputs context bug in workflow-level concurrency](https://github.com/orgs/community/discussions/45734) -- MEDIUM confidence (community, but verified behavior)
- Ferry codebase: `trigger.py`, `constants.py`, `dispatch.py`, `parse_payload.py`, `action/setup/action.yml` -- HIGH confidence (direct code reading)
- Ferry test repo: `ferry-test-app/.github/workflows/ferry-*.yml` -- HIGH confidence (direct code reading)
