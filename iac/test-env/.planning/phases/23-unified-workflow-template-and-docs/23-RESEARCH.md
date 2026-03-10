# Phase 23: Unified Workflow Template and Docs - Research

**Researched:** 2026-03-10
**Domain:** GitHub Actions YAML workflow template + Markdown documentation editing
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Matrix strategy for ALL resource types** - Lambda, Step Functions, and API Gateway deploy jobs all use `strategy.matrix` with `fail-fast: false`. No special-casing for SF/APGW. Prior "sequential loop" requirement is overridden — matrix for all.

2. **One workflow-level `env:` block** - `AWS_ROLE_ARN` (from secrets) and `AWS_REGION` set once at the workflow level. All jobs inherit — no repetition per step or per job.

3. **Unified template lives in `setup.md` only** - Full `ferry.yml` template shown in `setup.md` — single source of truth. Type-specific pages (`lambdas.md`, `step-functions.md`, `api-gateways.md`) have their workflow template sections REMOVED. Type pages keep: ferry.yaml config, field reference, and type-specific details.

4. **Migration guide is a section in `setup.md`** - Not a separate page — short section within `setup.md`. Content: deploy ordering (add `ferry.yml` to user repo first, then deploy backend update). Minimal scope — only one test repo, no external users yet.

### Claude's Discretion

None captured during discussion.

### Deferred Ideas (OUT OF SCOPE)

None captured during discussion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WF-01 | `ferry.yml` has a shared `setup` job and three conditional deploy jobs with job-level `if` guards | ARCHITECTURE.md + STACK.md have the complete 4-job structure; `if: needs.setup.outputs.resource_type == 'lambda'` pattern verified against GHA docs |
| WF-02 | Lambda deploy job uses matrix strategy for parallel per-resource builds | Existing `ferry-lambdas.yml` uses this pattern; CONTEXT.md locks matrix for all types |
| WF-03 | Step Functions deploy job uses matrix strategy (CONTEXT.md overrides roadmap) | CONTEXT.md Decision #1 overrides sequential-loop requirement; same matrix pattern as lambda |
| WF-04 | API Gateway deploy job uses matrix strategy (CONTEXT.md overrides roadmap) | Same as WF-03 |
| WF-05 | Workflow uses `run-name` that displays resource type | PITFALLS.md Pitfall 5 and STACK.md document the `fromJson` guard pattern |
| WF-06 | No workflow-level concurrency (only job-level concurrency keyed by type) | PITFALLS.md Pitfall 1 + STACK.md Pattern 2; job-level `concurrency.group: ferry-deploy-<type>` |
| DOC-01 | `setup.md` updated with unified `ferry.yml` template + migration guide | CONTEXT.md Decision #3 and #4; file at `docs/setup.md` lines 54-66 replaced |
| DOC-02 | Type-specific pages have workflow sections removed | CONTEXT.md: lambdas.md lines 28-107, step-functions.md lines 26-87, api-gateways.md lines 28-90 |
</phase_requirements>

## Summary

Phase 23 produces two artifacts: (1) the `ferry.yml` workflow template (shown inline in `setup.md` as a code block) and (2) updated documentation across four Markdown files. Phase 22 is confirmed complete — the setup action already exposes `resource_type` output and the backend dispatches to `ferry.yml`. This phase has no code changes to Python files and no test changes; it is pure YAML template authoring and Markdown editing.

The complete workflow template is fully specified in the existing research (`STACK.md` "Unified ferry.yml Template" section). The key user decision from CONTEXT.md is that ALL three resource types use `strategy.matrix` — this means the SF and APGW deploy jobs are structurally identical to the lambda deploy job except for the action they call. The template also requires: one `env:` block at workflow level for `AWS_ROLE_ARN` and `AWS_REGION`, a `run-name` that shows the resource type, and job-level concurrency groups (no workflow-level concurrency).

Documentation changes are precise surgical edits: `setup.md` gets its "Workflow File Naming Convention" section (lines 54-66) replaced with the unified template + migration guide section; each of the three type pages gets its "Workflow File" section deleted entirely while all other content is preserved.

**Primary recommendation:** Write the complete `ferry.yml` template in `setup.md` as a fenced code block; remove the three `## Workflow File` sections from type pages; add a one-section migration guide at the bottom of `setup.md`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| GitHub Actions YAML | N/A | Workflow template syntax | Target execution platform; no alternatives |
| Markdown | N/A | Documentation format | Existing docs use Markdown |

### Supporting
No additional libraries. Phase 23 has zero Python code changes and no new dependencies.

### Alternatives Considered
None. CONTEXT.md locks all design decisions. There is no design ambiguity in this phase.

**Installation:**
```bash
# No new dependencies
```

## Architecture Patterns

### Recommended Project Structure

The only file created in the user's repo is `.github/workflows/ferry.yml`. No new files in the ferry repo itself.

```
docs/
├── setup.md          # MODIFY: replace "Workflow File Naming" section; add template + migration guide
├── lambdas.md        # MODIFY: delete "Workflow File" section (lines 28-107)
├── step-functions.md # MODIFY: delete "Workflow File" section (lines 26-87)
└── api-gateways.md   # MODIFY: delete "Workflow File" section (lines 28-90)
```

### Pattern 1: Unified ferry.yml Template Structure

**What:** One workflow file with: workflow-level `env:`, a `run-name`, `on.workflow_dispatch`, `permissions`, one `setup` job, three conditional deploy jobs each with `if:`, `strategy.matrix`, and job-level `concurrency`.

**When to use:** This IS the deliverable — the template users copy into `.github/workflows/ferry.yml`.

```yaml
# Source: STACK.md "Unified ferry.yml Template (Complete)" + CONTEXT.md decisions
name: Ferry Deploy

run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}"

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON) -- sent by Ferry App, not for manual use"
        required: true

env:
  AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}
  AWS_REGION: us-east-1                    # Adjust to your AWS region

permissions:
  id-token: write
  contents: read
  checks: write

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

  deploy-lambda:
    name: "Ferry: deploy ${{ matrix.name }}"
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
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
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
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}

  deploy-step-function:
    name: "Ferry: deploy ${{ matrix.name }}"
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
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}

  deploy-api-gateway:
    name: "Ferry: deploy ${{ matrix.name }}"
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
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}
```

**Key decisions reflected in template:**
- `env:` block at workflow level — `AWS_ROLE_ARN` and `AWS_REGION` set once; steps reference `${{ env.AWS_ROLE_ARN }}` and `${{ env.AWS_REGION }}`
- `run-name` with `fromJson` guard — shows `lambda`/`step_function`/`api_gateway` in GHA Actions UI; fallback `|| 'manual'` prevents crashes on manual trigger
- Job-level `concurrency` — one group per type, `cancel-in-progress: false` (deploys never interrupted mid-flight)
- All three deploy jobs use `strategy.matrix` with `fail-fast: false` (per CONTEXT.md Decision #1)
- No workflow-level `concurrency:` key

### Pattern 2: Documentation Section Removal

**What:** Three `## Workflow File` sections are deleted from type pages. No other content changes.

**Exact line ranges (from file analysis):**
- `docs/lambdas.md` lines 28-107: `## Workflow File` header through end of the YAML code block
- `docs/step-functions.md` lines 26-87: `## Workflow File` header through end of the YAML code block
- `docs/api-gateways.md` lines 28-90: `## Workflow File` header through end of the YAML code block

After deletion, the sections that remain in each type page are:
- `## ferry.yaml Configuration` (kept)
- `### Field Reference` table (kept)
- Type-specific detail sections (Magic Dockerfile / Variable Substitution / Terraform Lifecycle / Content-Hash Skip Detection / Spec Format) (kept)

### Pattern 3: setup.md Section Replacement

**What:** The "Workflow File Naming Convention" section (lines 54-66 of `setup.md`) is replaced with a new "Workflow File" section containing the full `ferry.yml` template and a migration guide sub-section.

**Current content being replaced (lines 54-66):**
```
## Workflow File Naming Convention
[table of ferry-lambdas.yml, ferry-step_functions.yml, ferry-api_gateways.yml]
...
```

**Replacement structure:**
```markdown
## Workflow File

[brief intro: single ferry.yml replaces per-type files]

```yaml
# .github/workflows/ferry.yml
[complete template — see Pattern 1 above]
```

### Migration Guide

[deploy ordering: add ferry.yml to user repo first, then deploy backend update]
[note to delete old per-type workflow files]
```

Also: update line 107 of `setup.md` — currently reads "Pass the role ARN as the `aws-role-arn` input in your workflow files (see the per-resource-type guides)." This should be updated to reference the unified `ferry.yml` since the per-resource-type workflow snippets are being removed.

Also: update line 112 of `setup.md` in the "How Dispatch Works" section — step 3 references `ferry-lambdas.yml` by name. After migration, this should say `ferry.yml`.

### Anti-Patterns to Avoid

- **Keeping any workflow snippets in type pages:** CONTEXT.md Decision #3 is explicit — type pages have workflow sections REMOVED entirely. Do not add any "minimal snippet" or "excerpt" to type pages as a compromise.
- **Creating a separate migration guide page:** CONTEXT.md Decision #4 — migration guide is a section within `setup.md`, not a new page.
- **Adding workflow-level `concurrency:`:** Pitfall 1 in PITFALLS.md — would cancel parallel type dispatches. No workflow-level concurrency block.
- **Using `${{ secrets.AWS_ROLE_ARN }}` in step inputs:** CONTEXT.md Decision #2 — env vars set once at workflow level, steps reference `${{ env.AWS_ROLE_ARN }}`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Type routing in workflow | Step-level `if` conditions on shared job | Job-level `if` guards on separate jobs | Step-level `if` still evaluates the `strategy.matrix` expression for non-matching types; job-level `if` skips the job entirely including matrix evaluation |
| Distinguishing parallel runs | No `run-name` | `run-name` with `fromJson` guard | Without `run-name`, three simultaneous dispatches all show as "Ferry Deploy" — indistinguishable in the Actions tab |
| Concurrency control | Workflow-level `concurrency:` | Job-level `concurrency:` per type | Workflow-level concurrency with `github.workflow` key would cancel parallel type dispatches (Pitfall 1); `inputs` context also broken at workflow level (GHA bug #45734) |

**Key insight:** The `if` guard at the job level is critical — not just for routing logic but as the safety guard that prevents `fromJson` on the matrix from running when no resources of that type exist. This is not duplicated in step-level conditions.

## Common Pitfalls

### Pitfall 1: workflow-level `concurrency:` Cancels Parallel Dispatches
**What goes wrong:** If a workflow-level `concurrency: group: ${{ github.workflow }}` (or similar) is added, two simultaneous dispatches to `ferry.yml` (lambda + SF) cancel each other. Only one resource type deploys.
**Why it happens:** GHA concurrency groups are keyed by string; multiple dispatches to the same workflow share the same `github.workflow` value.
**How to avoid:** No `concurrency:` key at the workflow level. Job-level concurrency groups with hardcoded type names only.
**Warning signs:** After a push affecting multiple types, only 1 workflow run completes; others show "Cancelled."

### Pitfall 2: `run-name` Expression Crashes on Manual Trigger
**What goes wrong:** `run-name: "Ferry Deploy: ${{ fromJson(inputs.payload).resource_type }}"` — if a developer manually triggers the workflow from the GHA UI with empty payload, this expression fails and the workflow crashes before any job starts.
**Why it happens:** `fromJson` on empty string or null throws a GHA expression error.
**How to avoid:** Guard with `${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}`.
**Warning signs:** Workflow fails immediately with an expression evaluation error on manual trigger.

### Pitfall 3: `env:` References in `if:` Conditions Are Not Supported
**What goes wrong:** Using `if: env.SOME_VAR == 'value'` on a job is NOT the correct pattern. The workflow-level `env:` block is for step inputs, not for `if:` conditions on jobs.
**Why it happens:** GHA `if:` expressions use `needs`, `github`, `inputs` contexts — not `env` context for routing logic.
**How to avoid:** Job routing always uses `needs.setup.outputs.resource_type == 'lambda'` — never `env.*` in `if:` conditions.
**Warning signs:** Job `if:` conditions silently always evaluate to false.

### Pitfall 4: Missing `checks: write` Permission Breaks PR Status Reporting
**What goes wrong:** The deploy actions post Check Run status to the PR. Without `checks: write` in the workflow permissions, the Check Run creation fails silently.
**Why it happens:** Workflows have restrictive default permissions. `id-token: write` and `contents: read` alone are not sufficient.
**How to avoid:** Preserve all three permissions from existing per-type workflows: `id-token: write`, `contents: read`, `checks: write`.
**Warning signs:** No Check Run appears on the PR even when the workflow runs.

### Pitfall 5: Updating Stale References in setup.md Body Text
**What goes wrong:** Beyond the "Workflow File Naming Convention" section, `setup.md` has references to per-type filenames in prose:
- Line 107: "Pass the role ARN as the `aws-role-arn` input in your workflow files (see the per-resource-type guides)."
- Line 117: Step 3 of "How Dispatch Works" references `ferry-lambdas.yml` by name.
- Lines 125-130: "Per-Resource-Type Guides" section links to per-type guides but the note about per-type workflow setup remains valid (those pages still exist, just without workflow sections).
**How to avoid:** Read the full `setup.md` body text carefully; update any prose reference to per-type workflow filenames.

## Code Examples

Verified patterns from direct codebase analysis and existing research:

### Workflow env: Block (CONTEXT.md Decision #2)
```yaml
# Source: CONTEXT.md Decision #2
env:
  AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}
  AWS_REGION: us-east-1

# Steps reference via:
#   aws-role-arn: ${{ env.AWS_ROLE_ARN }}
#   aws-region: ${{ env.AWS_REGION }}
```

### run-name with Guard (Pitfall 2 prevention)
```yaml
# Source: PITFALLS.md Pitfall 5 + Pitfall 10
run-name: "Ferry Deploy: ${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).resource_type || 'manual' }}"
```

Note: `run-name` must use `github.event.inputs.payload` (not `inputs.payload`) — the `inputs` context is not available outside of job steps for some GHA contexts.

### Job-level if + concurrency (no workflow-level concurrency)
```yaml
# Source: STACK.md Pattern 2, PITFALLS.md Pitfall 1
  deploy-lambda:
    needs: setup
    if: needs.setup.outputs.resource_type == 'lambda'
    concurrency:
      group: ferry-deploy-lambda
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
```

### setup job outputs (both matrix and resource_type)
```yaml
# Source: action/setup/action.yml (Phase 22 output, confirmed complete)
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
```

### Migration Guide Content
```markdown
## Migration from Per-Type Workflows

If you have the previous three-file setup (`ferry-lambdas.yml`,
`ferry-step_functions.yml`, `ferry-api_gateways.yml`), follow this
deploy order to avoid a gap in deployments:

1. Add `.github/workflows/ferry.yml` to your repository and merge it
   to your default branch.
2. Deploy the updated Ferry backend (if self-hosting) or confirm the
   hosted Ferry App has been updated.
3. Delete the old per-type workflow files from your repository.

Deploy in this order because the Ferry App dispatches to `ferry.yml`
by name. If you deploy the backend before `ferry.yml` exists on the
default branch, all dispatches return 404 and no deployments run.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-type workflow files (`ferry-lambdas.yml` etc.) | Single `ferry.yml` | v1.4 (this phase) | Users maintain one file instead of three |
| Per-type workflow links in type pages | Unified template in `setup.md` only | v1.4 (this phase) | Single source of truth; type pages focus on resource config only |
| No `run-name` | `run-name` with `fromJson` guard | v1.4 (this phase) | Distinguishable workflow run names in GHA Actions tab |

**Deprecated/outdated:**
- `ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`: replaced by `ferry.yml` in v1.4
- `## Workflow File Naming Convention` section in `setup.md`: replaced by `## Workflow File` section
- Per-type `## Workflow File` sections in type pages: removed entirely

## Open Questions

None. All design decisions are locked by CONTEXT.md. Template is fully specified. Exact line ranges for doc edits are known.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | No automated tests for YAML template or Markdown docs |
| Config file | N/A |
| Quick run command | Manual inspection only |
| Full suite command | `uv run pytest tests/ -x -q` (verifies no Python regressions from doc-only phase) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WF-01 | `ferry.yml` has setup job + 3 conditional deploy jobs | manual | Inspect YAML structure | N/A (new file) |
| WF-02 | Lambda job uses matrix strategy | manual | Inspect YAML | N/A (new file) |
| WF-03 | SF job uses matrix strategy | manual | Inspect YAML | N/A (new file) |
| WF-04 | APGW job uses matrix strategy | manual | Inspect YAML | N/A (new file) |
| WF-05 | `run-name` shows resource type | manual | Inspect YAML | N/A (new file) |
| WF-06 | No workflow-level concurrency; job-level groups exist | manual | Inspect YAML | N/A (new file) |
| DOC-01 | `setup.md` has unified template + migration guide | manual | Read `docs/setup.md` | Yes (modify existing) |
| DOC-02 | Type pages have workflow sections removed | manual | Read type pages | Yes (modify existing) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q` (regression check — no Python changed, should be 50 tests passing)
- **Per wave merge:** Same
- **Phase gate:** Manual review of `docs/setup.md` (template present, migration guide present), `docs/lambdas.md` (workflow section absent), `docs/step-functions.md` (workflow section absent), `docs/api-gateways.md` (workflow section absent)

### Wave 0 Gaps
None — no new test files needed. Phase 23 changes are YAML template authoring and Markdown editing only. The Python test suite (50 tests) provides regression coverage.

## Exact File Change Inventory

### Files to Modify (4 files)

| File | Path | Change Type | Exact Scope |
|------|------|-------------|-------------|
| setup.md | `docs/setup.md` | Section replace + prose updates | Replace lines 54-66 (Workflow File Naming Convention); update line 107 OIDC section; update line 117 dispatch steps; add migration guide |
| lambdas.md | `docs/lambdas.md` | Section delete | Remove lines 28-107 (`## Workflow File` through end of code block) |
| step-functions.md | `docs/step-functions.md` | Section delete | Remove lines 26-87 (`## Workflow File` through end of code block) |
| api-gateways.md | `docs/api-gateways.md` | Section delete | Remove lines 28-90 (`## Workflow File` through end of code block) |

### Files NOT Changed
- All Python source files (no code changes in this phase)
- All test files
- All action YAML files (Phase 22 completed these)
- `docs/setup-runbook.md` (no workflow content there)

### No New Files Created
The `ferry.yml` template is shown as an inline code block in `setup.md` — it is not a file in the ferry repo itself. Users copy it into their own repo.

## Sources

### Primary (HIGH confidence)
- `docs/setup.md` — direct line-by-line read; exact line ranges identified for replacement
- `docs/lambdas.md` — direct read; lines 28-107 confirmed as `## Workflow File` section
- `docs/step-functions.md` — direct read; lines 26-87 confirmed as `## Workflow File` section
- `docs/api-gateways.md` — direct read; lines 28-90 confirmed as `## Workflow File` section
- `.planning/phases/22-backend-action-changes/22-01-SUMMARY.md` — Phase 22 confirmed complete; `action/setup/action.yml` has `resource_type` output
- `.planning/research/STACK.md` — complete `ferry.yml` template with all inputs verified
- `.planning/research/ARCHITECTURE.md` — job structure, `if:` guard pattern, concurrency decisions
- `.planning/research/PITFALLS.md` — Pitfall 1 (concurrency), Pitfall 5 (`run-name`), Pitfall 10 (`fromJson` guard)
- `.planning/phases/23-unified-workflow-template-and-docs/23-CONTEXT.md` — locked decisions for matrix strategy, `env:` block, template location, migration guide scope
- `action/setup/action.yml` — confirmed `resource_type` output exists (Phase 22 output)

### Secondary (MEDIUM confidence)
- None needed — all findings from direct codebase and project research analysis

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Template content: HIGH — all decisions locked in CONTEXT.md; complete template in STACK.md; Phase 22 dependencies confirmed complete
- Documentation edits: HIGH — exact line ranges identified from direct file reads; section boundaries confirmed
- Pitfalls: HIGH — concurrency and `run-name` pitfalls documented with HIGH confidence from official GHA docs and previous project research
- Test/validation: HIGH — no new test infrastructure needed; regression suite already exists

**Research date:** 2026-03-10
**Valid until:** No expiry — findings based on current codebase state and locked design decisions
