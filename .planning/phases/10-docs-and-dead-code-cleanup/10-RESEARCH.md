# Phase 10: Docs and Dead Code Cleanup - Research

**Researched:** 2026-02-28
**Domain:** Documentation fixes + dead code removal
**Confidence:** HIGH

## Summary

Phase 10 is a pure maintenance phase: fix three workflow documentation files to include the `checks: write` permission and missing deploy-step inputs added in Phase 8, then remove two unused error classes from `ferry_utils/errors.py`. There is no new capability being built -- this closes gaps INT-01, INT-02, and FLOW-01 identified in the v1.0 milestone audit, plus resolves dead code tech debt.

The changes are entirely mechanical. All three gaps stem from the same root cause: Phase 8 added Check Run reporting (`report.py`) which requires (a) the `checks: write` workflow permission and (b) `trigger-sha` + `github-token` inputs on deploy steps, but the documentation written in Phase 7 predated Phase 8 and was never backfilled.

**Primary recommendation:** Make all doc and code edits in a single plan. The scope is small (3 file edits for docs, 1 file edit for dead code) and all changes are independent.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Remove `BuildError` and `DeployError` entirely from `ferry_utils/errors.py`
- Full cleanup: remove class definitions, re-exports from `__init__.py`, and `__all__` entries
- Add `checks: write` permission to all three workflow docs (`lambdas.md`, `step-functions.md`, `api-gateways.md`)
- Include explanatory comment on each permission line (per-line inline comments)
- Example style: `checks: write     # Check Run status reporting`
- Add `trigger-sha` and `github-token` as active (uncommented) inputs to the Lambda deploy step in `docs/lambdas.md`
- Also add `github-token` to Step Functions and API Gateway deploy docs for consistency
- `github-token` uses `${{ github.token }}` (auto-granted), NOT a PAT

### Claude's Discretion
- Comment formatting: whether to convert existing block comments above permissions to inline, or blend styles -- pick the cleanest approach
- Exact wording of inline permission comments

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

## Standard Stack

Not applicable -- this phase involves no new libraries, frameworks, or dependencies. It is purely documentation edits and dead code removal in existing files.

## Architecture Patterns

### Current State Analysis

**Documentation files to edit (3 files):**

| File | Permission Gap | Input Gap |
|------|---------------|-----------|
| `docs/lambdas.md` | Missing `checks: write` | Deploy step missing `trigger-sha` and `github-token` |
| `docs/step-functions.md` | Missing `checks: write` | Deploy step missing `github-token` |
| `docs/api-gateways.md` | Missing `checks: write` | Deploy step missing `github-token` |

**Dead code file to edit (1 file):**

| File | Dead Code |
|------|-----------|
| `utils/src/ferry_utils/errors.py` | `BuildError` and `DeployError` classes defined but never imported or used anywhere |

### Pattern: Permissions Block (Current)

All three workflow docs currently have this permissions block:

```yaml
# OIDC requires id-token:write to request the JWT
# contents:read is needed to check out the repository
permissions:
  id-token: write
  contents: read
```

The existing style uses a **block comment above** the permissions section explaining each permission. The user decision is to add per-line inline comments.

### Pattern: Permissions Block (Target)

Recommended approach -- convert to per-line inline comments for self-documenting style:

```yaml
permissions:
  id-token: write    # OIDC JWT for AWS authentication
  contents: read     # Repository checkout
  checks: write      # Check Run status reporting
```

This replaces the block comment above with inline comments on each line. Every permission self-documents its purpose. This is cleaner than having both a block comment above and inline comments on the new line.

### Pattern: Lambda Deploy Step (Current vs Target)

**Current** (`docs/lambdas.md` lines 95-104):
```yaml
      - name: Deploy Lambda
        uses: ./action/deploy
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          image-uri: ${{ steps.build.outputs.image-uri }}
          image-digest: ${{ steps.build.outputs.image-digest }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
```

**Target** -- add `trigger-sha` and `github-token`:
```yaml
      - name: Deploy Lambda
        uses: ./action/deploy
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          image-uri: ${{ steps.build.outputs.image-uri }}
          image-digest: ${{ steps.build.outputs.image-digest }}
          deployment-tag: ${{ matrix.deployment_tag }}
          trigger-sha: ${{ matrix.trigger_sha }}       # For Check Run attachment
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
          github-token: ${{ github.token }}             # Check Run reporting (not a PAT)
```

### Pattern: SF/APIGW Deploy Steps (Current vs Target)

Step Functions and API Gateway deploy docs already have `trigger-sha` but are missing `github-token`. Only `github-token` needs to be added.

**SF deploy action inputs** (`action/deploy-stepfunctions/action.yml`): has `github-token` input (required: false, default: "")
**APIGW deploy action inputs** (`action/deploy-apigw/action.yml`): has `github-token` input (required: false, default: "")

Both actions pass `GITHUB_TOKEN: ${{ inputs.github-token }}` to their env block, and `report.py` reads `GITHUB_TOKEN` from env. So the docs need `github-token: ${{ github.token }}` for Check Run reporting to work.

### Pattern: github-token Dual Purpose

Important distinction for documentation clarity:
- **Build action** (`action/build/action.yml`): `github-token` is for **private repo dependencies** (passed as `INPUT_GITHUB_TOKEN` for pip auth). Comment: `# Uncomment for private repo deps`
- **Deploy actions**: `github-token` is for **Check Run reporting** (passed as `GITHUB_TOKEN` for GitHub API auth). Comment should clarify this is auto-granted, not a PAT.

### Dead Code Removal

**Verified unused:** `BuildError` and `DeployError` exist only in `utils/src/ferry_utils/errors.py` lines 24-29. Grep confirms they are never imported or referenced from any other file. They are NOT re-exported from `utils/src/ferry_utils/__init__.py` and are NOT in any `__all__` list. The cleanup is simply removing the two class definitions from `errors.py`.

## Don't Hand-Roll

Not applicable -- no custom solutions needed. This is mechanical editing.

## Common Pitfalls

### Pitfall 1: Confusing github-token Purpose Between Build and Deploy
**What goes wrong:** Documenting deploy's `github-token` as being for "private repo deps" (which is the build action's purpose).
**Why it happens:** Both build and deploy actions have a `github-token` input, but for different reasons.
**How to avoid:** Use distinct inline comments. Build: "for private repo deps". Deploy: "for Check Run reporting". The deploy `github-token` uses `${{ github.token }}` (auto-granted), not `${{ secrets.GH_PAT }}`.
**Warning signs:** If the doc example uses `${{ secrets.GH_PAT }}` for a deploy step.

### Pitfall 2: Forgetting github-token on SF/APIGW Deploy Docs
**What goes wrong:** Only adding `github-token` to `docs/lambdas.md` and forgetting the other two.
**Why it happens:** The audit (INT-02) only explicitly called out `docs/lambdas.md` for missing inputs. But all three deploy actions accept `github-token`.
**How to avoid:** The CONTEXT.md decision explicitly requires adding `github-token` to all three deploy docs for consistency.
**Warning signs:** Step Functions or API Gateway workflows that silently skip Check Runs.

### Pitfall 3: Leaving Block Comment Above Permissions AND Adding Inline
**What goes wrong:** Ending up with redundant documentation -- a block comment explaining permissions AND inline comments repeating the same information.
**Why it happens:** Being conservative about removing existing content.
**How to avoid:** Replace the block comment with inline comments on each permission line. The user decision is for per-line inline comments, and Claude's discretion is to pick the cleanest approach.

### Pitfall 4: Incomplete Dead Code Cleanup
**What goes wrong:** Removing class definitions but leaving orphaned imports or `__all__` entries.
**Why it happens:** Not checking all export paths.
**How to avoid:** Verified: `BuildError` and `DeployError` are NOT in `__init__.py` and NOT in any `__all__`. Only the class definitions in `errors.py` need to be removed.

## Code Examples

### Exact Current State: errors.py (Lines to Remove)

```python
# utils/src/ferry_utils/errors.py -- lines 24-29 (REMOVE)
class BuildError(FerryError):
    """Container image build or push failed."""


class DeployError(FerryError):
    """AWS resource deployment failed (Lambda, Step Functions, API Gateway)."""
```

After removal, the file should end at line 22 (after `ConfigError`).

### Exact Current State: Permissions Block (All 3 Docs)

```yaml
# OIDC requires id-token:write to request the JWT
# contents:read is needed to check out the repository
permissions:
  id-token: write
  contents: read
```

### Target State: Permissions Block (All 3 Docs)

```yaml
permissions:
  id-token: write    # OIDC JWT for AWS authentication
  contents: read     # Repository checkout
  checks: write      # Check Run status reporting
```

### Target: Lambda Deploy Step Additions

Add after `deployment-tag` line (line 102) and before `aws-role-arn` line:
```yaml
          trigger-sha: ${{ matrix.trigger_sha }}       # Git SHA for Check Run attachment
```

Add after `aws-region` line (last input):
```yaml
          github-token: ${{ github.token }}             # Check Run reporting (auto-granted, not a PAT)
```

### Target: SF Deploy Step Addition

Add after `aws-region` line:
```yaml
          github-token: ${{ github.token }}             # Check Run reporting (auto-granted, not a PAT)
```

### Target: APIGW Deploy Step Addition

Add after `aws-region` line:
```yaml
          github-token: ${{ github.token }}             # Check Run reporting (auto-granted, not a PAT)
```

## State of the Art

Not applicable -- no technology decisions or evolving library landscape. This is documentation maintenance.

## Open Questions

None. All decisions are locked, all files are identified, and the exact edits are known.

## Sources

### Primary (HIGH confidence)
- Direct file reads of all affected files in the repository:
  - `docs/lambdas.md` -- current permissions and deploy step
  - `docs/step-functions.md` -- current permissions and deploy step
  - `docs/api-gateways.md` -- current permissions and deploy step
  - `utils/src/ferry_utils/errors.py` -- `BuildError` and `DeployError` definitions
  - `utils/src/ferry_utils/__init__.py` -- no re-exports of dead code
  - `action/deploy/action.yml` -- `trigger-sha` and `github-token` inputs
  - `action/deploy-stepfunctions/action.yml` -- `github-token` input
  - `action/deploy-apigw/action.yml` -- `github-token` input
  - `action/build/action.yml` -- `github-token` for private repo deps (contrast)
  - `action/src/ferry_action/report.py` -- reads `GITHUB_TOKEN` from env for Check Runs
- Grep across entire codebase confirming `BuildError`/`DeployError` are unused
- `.planning/v1.0-MILESTONE-AUDIT.md` -- INT-01, INT-02, FLOW-01 gap definitions

## Metadata

**Confidence breakdown:**
- Standard stack: N/A -- no libraries involved
- Architecture: HIGH -- direct file reads confirm exact current state and required changes
- Pitfalls: HIGH -- all edge cases verified via codebase inspection

**Research date:** 2026-02-28
**Valid until:** indefinite (static codebase state, no external dependencies)
