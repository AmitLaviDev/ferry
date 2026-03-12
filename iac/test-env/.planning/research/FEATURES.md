# Feature Landscape: PR Integration (v2.0)

**Domain:** PR-triggered plan/apply deployment model for serverless deploy tool
**Researched:** 2026-03-12
**Scope:** Adding PR-triggered preview ("ferry plan"), merge/comment-triggered deploy ("ferry apply"), mid-way deployments, environment mapping, and GitHub Environment support

## Table Stakes

Features users expect from a PR integration layer. Missing = the feature feels broken or incomplete compared to Atlantis/Digger/Vercel.

| Feature | Why Expected | Complexity | Depends On |
|---------|--------------|------------|------------|
| Auto-plan on PR open/sync | Every competitor (Atlantis, Digger, Terraform Cloud, Vercel) auto-runs a preview when a PR is opened or updated. Users expect to see what will deploy without manual action | Medium | Backend: new `pull_request` event handler; reuse existing `match_resources` + `detect_config_changes` |
| Plan posted as PR comment | Atlantis and Digger both post plan output as a PR comment (not just a Check Run). Comments persist across pushes and are more visible than Check Runs for multi-resource previews | Low | Existing `post_pr_comment` function; new formatting for plan output |
| Update-in-place comment (not spam new comments) | Atlantis and Digger both update their existing comment on re-plan rather than posting a new one per push. Multiple comments per PR is universally considered noisy | Medium | Need to find existing Ferry comment (search by bot + marker), then PATCH instead of POST. GitHub Issues Comments API supports edit |
| Auto-deploy on merge to target branch | The core "ferry apply" path: when a PR merges to `main`, affected resources deploy. This is what v1.0-v1.5 already does for push events, but v2.0 must explicitly tie it to the PR lifecycle | Low | Already works -- push event on default branch triggers dispatch. Need to connect PR number to the deployment for traceability |
| Deploy status reported back to PR | After merge-triggered deploy, the user must see whether it succeeded or failed on the PR. Vercel posts deployment status; Atlantis posts apply output | Medium | Need a reporting mechanism: post-deploy comment on the merged PR, or update a Deployment Status via GitHub Deployments API |
| `/ferry apply` comment trigger for mid-way deploy | Digger uses `digger apply`, Atlantis uses `atlantis apply`. This is table stakes for any plan/apply tool. Allows deploying from a PR before merge (to staging, preview, etc.) | Medium-High | Backend: new `issue_comment` webhook handler; must detect `/ferry apply` in comment body, validate commenter permissions, extract PR context (branch, SHA), then dispatch |
| Environment-aware ferry.yaml | Users need to map branches to environments so `/ferry apply` knows WHERE to deploy. Without this, mid-way deploys have no target. Every deployment tool supports environment configuration | Medium | Schema extension to `ferry.yaml` v2: `environments:` block with branch-to-environment mapping |
| Plan shows target environment | When the plan preview posts, it must say "This will deploy to **staging**" not just list resources. Environment context is critical for understanding impact | Low | Requires environment resolution (branch -> environment mapping) during plan |
| Config error handling for new event types | Config errors on `pull_request` events must surface the same way as push events (PR comment with error details) | Low | Existing `ConfigError` handling + `post_pr_comment`; extend to new code paths |
| `/ferry plan` comment trigger for manual re-plan | Sometimes auto-plan misses edge cases or users want to re-run after external changes. Atlantis supports `atlantis plan` to force re-plan | Low | Same `issue_comment` handler as `/ferry apply`; dispatch to plan path instead |

## Differentiators

Features that set Ferry apart from Atlantis/Digger/Terraform Cloud. Not expected by default, but high value.

| Feature | Value Proposition | Complexity | Depends On |
|---------|-------------------|------------|------------|
| GitHub Environment integration (native secrets/vars) | Workflow jobs use `environment: staging` so GHA natively injects environment-level secrets and variables. No other serverless deploy tool does this -- Atlantis/Digger handle Terraform vars, not GHA Environment secrets | Medium | Dispatch payload must include `environment` field; workflow template uses `environment: ${{ needs.setup.outputs.environment }}` on deploy jobs. Requires ferry.yaml to define environment names matching GHA Environment names |
| Deployment protection rules (approval gates) | GHA Environments support required reviewers before deployment proceeds. Ferry can leverage this for production deploys -- no custom approval logic needed, just use GHA's built-in gates | Low | Zero Ferry code -- entirely GHA Environment config. Just document the pattern: create a `production` GHA Environment with required reviewers, ferry.yaml maps `main` -> `production` |
| Check Run + Comment (dual reporting) | Post both a Check Run (shows in PR checks tab, blocks merge if desired) AND a comment (visible in conversation). Atlantis does comment-only; Terraform Cloud does Check Run only. Both channels gives best visibility | Low | Already have both `create_check_run` and `post_pr_comment`. Use Check Run for pass/fail status (merge gating), comment for detailed plan output |
| Collapsible plan output for large changes | When 10+ resources are affected, the plan comment becomes unwieldy. Use `<details>` HTML tags to collapse per-type sections. Atlantis has had long-standing issues with large plan output overflowing comments | Low | Markdown formatting in plan comment builder |
| Content-hash preview in plan | Show whether each resource would actually deploy or skip (content unchanged). Current content-hash check happens at deploy time in the action; surfacing it at plan time tells the user "this Lambda changed files but the build output is identical, so it will be a no-op" | High | Would require running the build (or at least computing the hash) during plan phase. Likely too expensive for v2.0 MVP. Flag as future differentiator |
| Concurrent PR isolation | Two PRs changing the same resource should not block each other's plans (unlike Atlantis which locks per-directory). Ferry's plan is read-only (no state to lock), so natural isolation | None | Already inherent -- plan is just change detection, no shared state. Worth documenting as a selling point vs Atlantis |
| Branch deploy (deploy PR branch to non-prod) | `/ferry apply staging` deploys the PR's HEAD commit to staging without merging. The Lambda/SF/APGW gets the PR's code in a specific environment. Useful for QA before merge | High | Requires dispatching with PR branch SHA (not merge commit), environment parameter, and potentially different ECR tags or Lambda aliases per environment |
| Stale plan detection | If the target branch has new commits since the plan was generated, warn the user that the plan may be outdated. Terraform has built-in stale plan detection; Atlantis re-plans automatically | Medium | Compare plan's `trigger_sha` against current branch HEAD. If different, add a warning banner to the plan comment or require re-plan |

## Anti-Features

Features to explicitly NOT build for v2.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Ephemeral preview environments (auto-create Lambda/SF per PR) | Requires creating and destroying AWS resources dynamically (new Lambda functions, new ECR repos, new API Gateway stages per PR). Massively increases scope, cost, and complexity. Vercel can do this because they own the hosting platform; Ferry deploys to user's AWS | Deploy to pre-existing staging environment. User's IaC defines the staging Lambda/SF/APGW; Ferry deploys PR code to them via environment mapping |
| Terraform plan execution (actual `terraform plan` output) | Ferry deploys code to existing infrastructure. It does not manage infrastructure. Running `terraform plan` would require Terraform state access, provider credentials, and is a fundamentally different tool | Show which resources will be DEPLOYED (code changes), not which infrastructure will change. Ferry's "plan" is a change detection preview, not a Terraform plan |
| Auto-merge after successful deploy | Dangerous and opinionated. If deploy to staging succeeds, some tools auto-merge the PR. This bypasses code review and is an anti-pattern for most teams | Deploy and report status. Merge decision is human |
| PR-level locking (Atlantis-style) | Atlantis locks state files per PR to prevent concurrent applies. Ferry has no shared state to lock -- each deploy is independent (update Lambda code, update SF definition). Locking would add complexity with zero benefit | No locking needed. Ferry deploys are idempotent: last deploy wins. If two PRs deploy to the same Lambda, the last merge wins (same as any CD tool) |
| Rollback on failed deploy | Cross-resource rollback is unsolved for serverless (what if Lambda succeeds but SF fails?). Adding rollback for v2.0 would be a massive scope increase | Report failure clearly. User fixes and re-pushes. Previous version is still in ECR; user can re-deploy manually if urgent |
| Custom slash commands beyond plan/apply | Supporting `/ferry lock`, `/ferry unlock`, `/ferry destroy`, etc. adds maintenance burden for rarely-used features | Start with `/ferry plan` and `/ferry apply [environment]`. Add more commands only if user demand justifies it |
| Multi-account deploy from PR | Deploying to different AWS accounts per environment (staging in account A, prod in account B) requires multiple OIDC role ARNs and complex credential routing | Single AWS account per workflow run. Different environments use different Lambda function names / SF names / APGW stages within the same account. Multi-account is v3+ |
| Deployment queue/ordering across PRs | If PR-1 and PR-2 both merge close together, ensuring PR-1 deploys before PR-2 requires a queue. This is the Digger "Run Queue" pattern | GitHub's merge order determines deploy order. Push events fire in merge order. If user needs strict ordering, use GitHub merge queue (native feature) |
| Dashboard for deployment history | Building a UI to show deployment history across PRs is a significant frontend investment | PR is the dashboard. Each PR's comments show plan + apply results. GitHub's deployments tab shows deployment history natively if we use the Deployments API |

## Feature Dependencies

```
ferry.yaml v2 schema (environments block)
    |
    +---> Environment resolution (branch -> environment mapping)
    |         |
    |         +---> Plan comment includes target environment
    |         |
    |         +---> Dispatch payload includes environment field
    |                   |
    |                   +---> Workflow template uses `environment:` on deploy jobs
    |                   |         |
    |                   |         +---> GHA injects environment-level secrets/vars
    |                   |
    |                   +---> `/ferry apply [env]` targets specific environment
    |
    v
Backend: pull_request event handler (auto-plan)
    |
    +---> Reuses existing change detection (match_resources, detect_config_changes)
    |
    +---> Plan comment formatting + update-in-place
    |
    +---> Check Run creation (reuse existing create_check_run)
    |
    v
Backend: issue_comment event handler (/ferry apply, /ferry plan)
    |
    +---> Comment parsing (detect slash command + optional env arg)
    |
    +---> Permission validation (commenter has write access?)
    |
    +---> PR context extraction (branch, HEAD SHA, PR number)
    |         |
    |         +---> Need GitHub API call: get PR details from issue_comment payload
    |
    +---> Environment resolution (explicit env arg or branch-default mapping)
    |
    +---> Dispatch (reuse trigger_dispatches with env-aware payload)
    |
    v
Deploy status reporting
    |
    +---> Post-deploy comment on PR (success/failure summary)
    |
    +---> GitHub Deployments API integration (optional, enhances visibility)
```

### Dependency Detail

1. **ferry.yaml v2 schema** is the foundation. Without environment definitions, mid-way deploys and GitHub Environment integration have no target. This must come first.

2. **`pull_request` event handler** is independent of environments. Auto-plan works with or without environment mapping -- it just shows which resources would deploy. But it benefits from environment resolution to show "will deploy to staging."

3. **`issue_comment` handler** depends on the PR context extraction (getting branch/SHA from a PR referenced by issue number) and environment resolution. It also depends on dispatch having an environment field.

4. **GitHub Environment integration** depends on environment being in the dispatch payload AND the workflow template using `environment:` on deploy jobs. This is a coordination point between backend, action, and workflow template.

5. **Deploy status reporting** depends on dispatch working (so there are results to report). It can initially be a simple PR comment; GitHub Deployments API integration can come later.

### Critical Path (minimum viable PR integration)

```
ferry.yaml v2 schema  -->  pull_request handler  -->  plan comment
                                                          |
                                                          v
                                               issue_comment handler  -->  /ferry apply dispatch
                                                                              |
                                                                              v
                                                                     deploy status on PR
```

Environment mapping and GHA Environment integration can be added incrementally after the core plan/apply loop works.

## Existing Infrastructure Reuse

The following v1.x components are directly reusable for v2.0:

| Component | Current Use | v2.0 Reuse |
|-----------|------------|------------|
| `match_resources()` | Push change detection | Plan: detect what would deploy from PR diff |
| `detect_config_changes()` | Config diff detection | Plan: detect config changes in PR |
| `get_changed_files()` | Commit diff via GitHub API | Plan: PR diff (three-dot compare against target branch) |
| `create_check_run()` | PR preview on push | Plan: Check Run with plan summary |
| `post_pr_comment()` | Config error reporting | Plan: detailed plan comment |
| `format_deployment_plan()` | Check Run text formatting | Plan: comment body (with enhancements) |
| `trigger_dispatches()` | Push deploy dispatch | Apply: dispatch with environment context |
| `build_deployment_tag()` | Deploy tag generation | Apply: tag with environment prefix |
| `verify_signature()` | Webhook auth | All new event types |
| `is_duplicate()` | Webhook dedup | All new event types |
| `fetch_ferry_config()` | Config loading | Plan + Apply: load config from PR branch |
| `BatchedDispatchPayload` | Deploy payload | Apply: extended with environment field |

The reuse surface is substantial. The core plan logic is "run change detection and format the output as a comment." The core apply logic is "run trigger_dispatches with extra context." The NEW code is primarily: event routing (PR and comment events), environment resolution, comment update-in-place, and status reporting.

## Webhook Events Required

| Event | GitHub Header | When Fires | Ferry Use |
|-------|--------------|------------|-----------|
| `push` (existing) | `x-github-event: push` | On every push to any branch | Default branch: auto-deploy (existing v1.x). Non-default: auto-plan (v2.0 enhancement) |
| `pull_request` | `x-github-event: pull_request` | PR opened, synchronized, reopened, closed | `opened/synchronize/reopened`: auto-plan. `closed + merged`: could trigger apply (alternative to push event) |
| `issue_comment` | `x-github-event: issue_comment` | Comment created on issue/PR | Detect `/ferry plan` and `/ferry apply [env]` commands |

**Important `issue_comment` nuance**: The payload does NOT include full PR details. The `issue` object has a `pull_request` key (with just a URL) if the comment is on a PR. Ferry must make an additional API call (`GET /repos/{owner}/{repo}/pulls/{number}`) to get the PR's head SHA, base branch, and merge status. This is confirmed by GitHub docs and Digger/Atlantis implementations.

**Event selection for auto-plan**: Use `push` event (already received) rather than subscribing to `pull_request`. The handler already receives push events for non-default branches and creates Check Runs. Extending this path to also post plan comments is simpler than adding a new event subscription. However, `pull_request` events provide richer context (PR number, base branch, merge status) that `push` events lack. **Recommendation**: Subscribe to `pull_request` events for auto-plan, keep `push` for deploy-on-merge.

## GitHub App Permission Updates

The Ferry GitHub App will need additional webhook subscriptions:

| Permission/Event | Current | v2.0 Needed | Why |
|-----------------|---------|-------------|-----|
| Pull requests (read) | Yes | Yes | Already have |
| Pull requests (write) | No | Yes | To post/update PR comments from issue_comment handler (already can post via issues API, but PR-specific operations may need this) |
| Issues (write) | Yes | Yes | Already have -- used for PR comments |
| Pull request events | No | Yes | Subscribe to `pull_request` webhook events |
| Issue comment events | No | Yes | Subscribe to `issue_comment` webhook events |
| Deployments (write) | No | Optional | To create GitHub Deployments for enhanced visibility |
| Environments (read) | No | Optional | To validate environment names against GHA Environments |

## Plan Comment Format (Proposed)

Based on Atlantis and Digger patterns, adapted for Ferry's serverless context:

```markdown
## Ferry: Deployment Plan

**Target:** `staging` (branch `feature/new-api` -> `main`)
**Commit:** `abc1234`

### Resources affected (5)

<details>
<summary>Lambdas (3)</summary>

| Resource | Change | Source |
|----------|--------|--------|
| ~ **order-processor** | modified | `services/order-processor/handler.py` |
| ~ **payment-handler** | modified | `services/payment-handler/utils.py` |
| + **notification-sender** | new | `services/notification-sender/` |

</details>

<details open>
<summary>Step Functions (1)</summary>

| Resource | Change | Source |
|----------|--------|--------|
| ~ **checkout-flow** | modified | `workflows/checkout/definition.json` |

</details>

<details>
<summary>API Gateways (1)</summary>

| Resource | Change | Source |
|----------|--------|--------|
| ~ **main-api** | modified | `definitions/api_gateway.yaml` |

</details>

---
*Ferry will deploy these resources when this PR is merged to `main`.*
*To deploy now: comment `/ferry apply staging`*

<!-- ferry:plan:marker -->
```

Key design decisions:
- **Collapsible sections** (`<details>`) prevent comment bloat with many resources
- **Table format** is scannable (vs. Atlantis's raw text dump)
- **HTML comment marker** (`<!-- ferry:plan:marker -->`) enables find-and-update of existing comment
- **Environment callout** at top makes deployment target immediately clear
- **Action prompt** at bottom tells users how to deploy mid-way

## Environment Mapping Design (Proposed ferry.yaml v2)

```yaml
version: 2

environments:
  staging:
    branches: ["develop", "feature/*"]
  production:
    branches: ["main"]

lambdas:
  order-processor:
    source: services/order-processor
    ecr: ferry/order-processor
    # Resource definitions stay the same -- environments are orthogonal
```

Design principles:
- **Environments are global**, not per-resource. All resources deploy to the same environment when triggered.
- **Branch patterns** support exact match and glob. `feature/*` matches any feature branch.
- **No environment-specific resource overrides** in v2.0. The same Lambda function name deploys in all environments. If users need different function names per environment, that is handled via GHA Environment variables (e.g., `vars.LAMBDA_FUNCTION_NAME`), not ferry.yaml.
- **Default behavior** when no `environments:` block: `main` -> no specific environment (backward compatible with v1.x).

## MVP Recommendation

Prioritize (in implementation order):

1. **`pull_request` event handler + auto-plan** -- Subscribe to `pull_request` events, detect changes on PR open/sync, post plan as PR comment with update-in-place. This is the highest-visibility feature and reuses 80% of existing change detection code.

2. **Plan comment formatting** -- Collapsible per-type sections, table format, HTML comment marker for update-in-place. Builds on existing `format_deployment_plan`.

3. **ferry.yaml v2 schema: `environments:` block** -- Add optional `environments:` section with branch-to-environment mapping. Validate patterns. Keep backward compatible (missing environments block = v1.x behavior).

4. **Environment resolution** -- Given a branch name, resolve to an environment using ferry.yaml patterns. Used by both plan (display) and apply (dispatch).

5. **`issue_comment` handler + `/ferry apply [env]`** -- Parse slash commands from PR comments, validate permissions, extract PR context (additional API call), resolve environment, dispatch deploy.

6. **Dispatch payload: environment field** -- Extend `BatchedDispatchPayload` with optional `environment` field. Setup action exposes it as output.

7. **Workflow template: `environment:` on deploy jobs** -- Deploy jobs use `environment: ${{ needs.setup.outputs.environment }}` so GHA injects environment-level secrets/vars.

8. **Deploy status reporting** -- After dispatch, post result (success/failure) back to the PR as a comment.

Defer to v2.1+:
- **GitHub Deployments API integration**: Enhanced visibility but not required for core plan/apply loop
- **`/ferry plan` manual re-plan**: Auto-plan covers the common case; manual re-plan is a convenience
- **Stale plan detection**: Nice-to-have warning when target branch has moved since plan was generated
- **Branch deploy (deploy PR branch to non-prod)**: Complex (different SHA routing), valuable for QA workflows
- **Content-hash preview in plan**: Would require running builds during plan phase -- expensive and slow
- **Deployment protection rules documentation**: Works out-of-the-box with GHA Environments; just needs a docs page

## Sources

- [Atlantis: Using Atlantis](https://www.runatlantis.io/docs/using-atlantis) -- Plan/apply comment model, autoplan on PR open (HIGH confidence)
- [Atlantis: Locking](https://www.runatlantis.io/docs/locking) -- Per-directory+workspace locks, concurrent PR isolation (HIGH confidence)
- [Atlantis: Server Configuration](https://www.runatlantis.io/docs/server-configuration.html) -- `enable-diff-markdown-format`, plan output rendering (MEDIUM confidence)
- [Atlantis: Diff markdown format issue (#2244)](https://github.com/runatlantis/atlantis/issues/2244) -- Plan output formatting challenges (MEDIUM confidence)
- [Digger: Building apply-after-merge workflow](https://medium.com/@DiggerHQ/building-apply-after-merge-workflow-in-digger-f59c6598be59) -- Apply-before-merge vs apply-after-merge, Run Queue concept (MEDIUM confidence)
- [Terraform Cloud: UI and VCS-driven run workflow](https://developer.hashicorp.com/terraform/cloud-docs/run/ui) -- Speculative plans on PR, auto-plan on PR update (HIGH confidence)
- [Terramate: Mastering Terraform Workflows](https://terramate.io/rethinking-iac/mastering-terraform-workflows-apply-before-merge-vs-apply-after-merge/) -- Stale plan detection, apply-before vs after merge tradeoffs (MEDIUM confidence)
- [GitHub Docs: Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) -- GHA Environments, secrets/vars, protection rules, branch restrictions (HIGH confidence)
- [GitHub Docs: Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) -- Deployment status reporting, environment parameter (HIGH confidence)
- [GitHub Docs: REST API endpoints for deployments](https://docs.github.com/en/rest/deployments/deployments) -- Deployments API for status tracking (HIGH confidence)
- [GitHub Blog: Enabling branch deployments through IssueOps](https://github.blog/engineering/engineering-principles/enabling-branch-deployments-through-issueops-with-github-actions/) -- IssueOps pattern for comment-triggered deploys (HIGH confidence)
- [GitHub Blog: IssueOps: Automate CI/CD with GitHub Issues and Actions](https://github.blog/engineering/issueops-automate-ci-cd-and-more-with-github-issues-and-actions/) -- IssueOps patterns (HIGH confidence)
- [peter-evans/slash-command-dispatch](https://github.com/peter-evans/slash-command-dispatch) -- Slash command -> repository_dispatch pattern for GHA (HIGH confidence)
- [GitHub Docs: Webhook events - issue_comment](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- issue_comment payload structure, PR detection via `issue.pull_request` key (HIGH confidence)
- [GitHub Blog: Actions pull_request_target and environment branch protections changes (2025-11-07)](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/) -- Environment branch protection now evaluates against default branch for pull_request_target (HIGH confidence)
- [Vercel: Deploying GitHub Projects](https://vercel.com/docs/git/vercel-for-github) -- Auto preview URL per PR, deployment status checks (HIGH confidence)
- [Netlify: Deploy Previews](https://docs.netlify.com/deploy/deploy-types/deploy-previews/) -- Preview URL per PR, comment with preview link (HIGH confidence)
- [AWS Blog: Previewing environments using containerized Lambda functions](https://aws.amazon.com/blogs/compute/previewing-environments-using-containerized-aws-lambda-functions/) -- Ephemeral Lambda preview environments (MEDIUM confidence)
- [ServerlessFirst: How to prevent concurrent deployments of serverless stacks in GitHub Actions](https://serverlessfirst.com/emails/how-to-prevent-concurrent-deployments-of-serverless-stacks-in-github-actions/) -- GHA concurrency groups for serverless deploy (MEDIUM confidence)
- Existing Ferry codebase: `handler.py`, `runs.py`, `trigger.py`, `schema.py`, `dispatch.py` models (PRIMARY source)
