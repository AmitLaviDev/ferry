# Domain Pitfalls: PR Integration (v2.0)

**Domain:** Adding PR-triggered plan/apply deployment, environment mapping, and GitHub Environments to an existing push-to-deploy serverless deployment tool
**Researched:** 2026-03-12
**Scope:** Common mistakes when adding these features to Ferry's existing v1.x push-to-deploy system

## Critical Pitfalls

Mistakes that cause security vulnerabilities, broken deploy flows, or require architectural rework.

### Pitfall 1: OIDC Sub Claim Changes When Adding GitHub Environments

**What goes wrong:** The existing v1.x push-to-deploy flow uses AWS OIDC with a trust policy conditioned on `repo:owner/repo:ref:refs/heads/main`. When you add GitHub Environments (e.g., `staging`, `production`) to the workflow, the OIDC sub claim silently changes to `repo:owner/repo:environment:production`. The existing IAM role trust policy rejects the new sub claim. All deploys break with `AccessDenied` -- and the error message does not mention the sub claim mismatch.

**Why it happens:** GitHub's OIDC provider uses mutually exclusive sub claim formats. When a job references an `environment:` field, the sub claim includes the environment name instead of the branch ref. You cannot have both `ref:refs/heads/main` AND `environment:production` in the same sub claim. This is a fundamental design choice in GitHub's OIDC implementation, not a bug.

**Consequences:** Every deploy fails silently from the user's perspective (GHA shows `Error: Could not assume role with OIDC`). The existing push-to-deploy flow breaks the moment environments are added to the workflow YAML, even if no other code changes. Users who have already configured IAM trust policies for Ferry v1.x will all break on upgrade.

**Prevention:**
- Update IAM trust policies BEFORE adding `environment:` to the workflow. The policy must include both patterns during migration:
  ```json
  "Condition": {
    "StringLike": {
      "token.actions.githubusercontent.com:sub": [
        "repo:owner/repo:ref:refs/heads/main",
        "repo:owner/repo:environment:staging",
        "repo:owner/repo:environment:production"
      ]
    }
  }
  ```
- Document the IAM trust policy change as a mandatory migration step, with exact policy JSON.
- Consider using the `environment` OIDC claim as an additional condition (not the sub) for environments, so the sub can remain branch-based. However, this requires custom OIDC claim templates via the GitHub REST API, which adds complexity.
- Test with `github/actions-oidc-debugger` to verify the actual sub claim before deploying.

**Detection:** `aws sts assume-role-with-web-identity` fails. GHA logs show OIDC token request succeeded but role assumption failed. Check the sub claim in the OIDC debugger output.

**Confidence:** HIGH -- verified from [GitHub OIDC reference docs](https://docs.github.com/actions/reference/openid-connect-reference) and [aws-actions/configure-aws-credentials#454](https://github.com/aws-actions/configure-aws-credentials/issues/454).

**Phase:** Must be addressed in the IAM/infrastructure phase, BEFORE the workflow template adds `environment:` fields.

---

### Pitfall 2: `issue_comment` Trigger Runs on Default Branch, Not PR Branch

**What goes wrong:** You add `/ferry apply` as a comment-triggered deploy command using the `issue_comment` event. The workflow fires, but it checks out and runs against the default branch (main), not the PR branch. The deploy runs against stale code -- whatever is on main, not the PR's code.

**Why it happens:** `issue_comment` is an event on the issue/PR metadata, not on the PR's code. GitHub always runs `issue_comment`-triggered workflows from the default branch's workflow file, with `GITHUB_SHA` pointing to the default branch's HEAD. The PR branch context is not available in `github.ref` or `github.sha` for `issue_comment` events. This is a fundamental GHA design decision documented in [community discussion #59389](https://github.com/orgs/community/discussions/59389) and [actions/checkout#331](https://github.com/actions/checkout/issues/331).

**Consequences:** If you use `issue_comment` for `/ferry apply` and naively run `actions/checkout@v4`, you deploy main, not the PR's code. This is a correctness bug that silently deploys the wrong code. For a plan command, you show a plan for main, not for the PR changes.

**Prevention:**
- Do NOT use `issue_comment` directly for code operations. Instead, use the Digger/Ferry App pattern: the backend (Lambda) receives the `issue_comment` webhook, validates the commenter's permissions, extracts the PR branch/SHA, and fires a `workflow_dispatch` with the correct ref and SHA in the payload. The workflow then checks out the correct commit.
- If using `issue_comment` directly in a workflow, extract the PR ref using the GitHub API:
  ```yaml
  - uses: xt0rted/pull-request-comment-branch@v3  # resolves PR head ref
  - uses: actions/checkout@v4
    with:
      ref: ${{ steps.comment-branch.outputs.head_ref }}
  ```
- Ferry's architecture (backend Lambda receives webhooks, fires `workflow_dispatch`) naturally avoids this pitfall since the backend can embed the correct SHA in the dispatch payload. This is the recommended approach.

**Detection:** Deploy from a `/ferry apply` comment, then verify the deployed code matches the PR branch, not main.

**Confidence:** HIGH -- documented GHA behavior, confirmed across [multiple community discussions](https://dev.to/zirkelc/trigger-github-workflow-for-comment-on-pull-request-45l2) and [checkout action docs](https://github.com/actions/checkout/issues/331).

**Phase:** Must be addressed in the backend webhook handler phase (PR event handling design).

---

### Pitfall 3: Anyone Who Can Comment Can Trigger `/ferry apply`

**What goes wrong:** You implement `/ferry apply` as a comment command. A contributor with read access (or even a random commenter on a public repo) writes `/ferry apply` on a PR. The deploy fires because no permission check was implemented -- the workflow or backend just pattern-matches the comment text.

**Why it happens:** GitHub allows anyone with comment permissions to write on a PR. The `issue_comment` event fires for ALL commenters regardless of their repository role. If the backend or workflow only checks `contains(comment.body, '/ferry apply')` without verifying the commenter's permission level, anyone can trigger deploys.

**Consequences:** Unauthorized deployments. In the worst case, a malicious actor comments `/ferry apply` on a PR containing destructive code changes (if the PR is from a collaborator) or uses it to flood deploy pipelines.

**Prevention:**
- The Ferry backend (Lambda) must check the commenter's permission level before triggering a dispatch. Use the GitHub API:
  ```
  GET /repos/{owner}/{repo}/collaborators/{username}/permission
  ```
  Only allow `admin` or `write` (or a configurable list) to trigger apply.
- Digger's approach: their orchestrator backend checks if the commenter is a collaborator before triggering the workflow. However, [Digger issue #577](https://github.com/diggerhq/digger/issues/577) shows this was initially missing -- they shipped without permission checks and had to add them later.
- Do NOT rely on workflow-level `if:` checks like `github.event.comment.author_association == 'MEMBER'` -- `author_association` can be stale and does not reflect current repository permissions accurately.
- Consider requiring PR approval before apply is allowed (plan shows on PR push, apply only after approval + `/ferry apply` from authorized user).

**Detection:** Have a read-only contributor comment `/ferry apply` on a PR. If a deploy triggers, the permission check is missing.

**Confidence:** HIGH -- well-documented pattern from Digger/Atlantis ecosystems. [Digger restrict apply user issue](https://github.com/diggerhq/digger/issues/577).

**Phase:** Must be addressed in the backend webhook handler phase, alongside `issue_comment` event handling.

---

### Pitfall 4: Breaking Push-to-Deploy While Adding PR Flow

**What goes wrong:** You modify the webhook handler to support `pull_request` and `issue_comment` events alongside `push`. A subtle bug in the event routing causes push events to be mishandled -- either they get filtered out, processed as PR events, or the dispatch payload gets wrong parameters (e.g., `pr_number` is populated from a closed/merged PR instead of being empty for direct pushes).

**Why it happens:** The current handler (line 102 of `handler.py`) has a simple guard: `if event_type != "push": return ignored`. Adding PR support means this guard must become a multi-event router. The handler's logic for extracting SHA, branch, and comparing changes is push-specific (e.g., `before_sha`, `after_sha` from push payload vs `pull_request.head.sha` from PR payload). Mixing these code paths without clean separation leads to bugs.

**Consequences:** The existing production deploy flow (push to main -> dispatch -> deploy) breaks. This is the worst outcome because you break working functionality while adding new functionality.

**Prevention:**
- **Isolate event handlers completely.** Do not add PR logic into the existing push handler. Create separate handler functions: `handle_push()`, `handle_pull_request()`, `handle_issue_comment()`. The top-level `handler()` routes by event type to isolated handlers that share no mutable state.
- **Keep the push flow byte-identical during PR integration.** The first phase of PR support should add new event handlers without touching the push path. Only after PR flow is proven in E2E should you refactor shared logic (change detection, dispatch building) into common utilities.
- **Integration tests for push regression.** Every PR integration phase must include a test that verifies the push -> dispatch -> deploy path still works unchanged.
- The current handler structure (steps 1-13 in `handler.py`) is already tightly coupled to push payloads. Factor extraction of SHA/branch/ref into a `PushContext` dataclass before adding PR context extraction.

**Detection:** After adding PR support, push a code change to main. If no dispatch fires, push handling is broken.

**Confidence:** HIGH -- direct analysis of `handler.py` structure. The tight coupling between event parsing and business logic makes this a near-certain risk without explicit isolation.

**Phase:** Must be addressed in the first PR integration phase. Event handler isolation is prerequisite to all other PR work.

---

### Pitfall 5: Stale Plan Applied After Code Changes

**What goes wrong:** A developer runs `/ferry plan` on a PR. The plan shows "Lambda X will be deployed with image abc123." The developer then pushes 3 more commits to the PR. Without re-planning, they run `/ferry apply`. The apply deploys the code from the plan (commit abc123), not the latest PR code -- or worse, it deploys the latest code but the plan output was misleading about what would actually be deployed.

**Why it happens:** The plan is a point-in-time snapshot tied to a specific commit SHA. If the plan output is stored or cached, it can become stale when new commits arrive. Unlike Terraform where the plan file is a serialized execution plan, Ferry's "plan" is informational (showing which resources will be affected). But the SHA embedded in the plan does not match the current PR head.

**Consequences:** User sees a plan for one version of code, approves it, then deploys different code. This breaks the review-then-deploy contract that plan/apply is supposed to provide. In Terraform ecosystems, this is the [#1 complaint about plan/apply workflows](https://github.com/runatlantis/atlantis/issues/1122) and the [root cause of most Atlantis incidents](https://github.com/runatlantis/atlantis/issues/1624).

**Prevention:**
- **Auto-invalidate plans on new pushes.** When a new push arrives on a PR branch, the backend should mark any existing plan as stale and re-run the plan automatically. The Check Run from the old plan should be replaced/updated to show "Plan outdated -- new commits detected."
- **Bind apply to a specific SHA.** The `/ferry apply` command should include the SHA it intends to deploy (either explicitly or by using the latest PR head SHA at command time). The backend verifies this SHA matches the last planned SHA. If not, reject the apply with "Plan is stale, please re-run plan."
- **Display the plan SHA prominently.** The Check Run or PR comment showing the plan should include the commit SHA: "Plan for commit abc123. Apply will deploy this exact commit."
- For Ferry specifically: since the "plan" is a Check Run showing affected resources (not a cached deploy artifact), the staleness risk is lower than Terraform. But the user's mental model still expects "I saw the plan, I approved it, apply deploys exactly what I saw."

**Detection:** Push new commits to a PR after planning, then apply without re-planning. Check if the deployed version matches the plan or the latest push.

**Confidence:** HIGH -- extensively documented in [Atlantis stale plans issue #1122](https://github.com/runatlantis/atlantis/issues/1122), [Atlantis apply picks up stale plans #1624](https://github.com/runatlantis/atlantis/issues/1624), and [Digger's apply-before-merge article](https://medium.com/@DiggerHQ/the-case-for-apply-before-merge-bc08a7a9bfea).

**Phase:** Must be addressed in the plan/apply state management phase. SHA binding is the core design decision.

---

### Pitfall 6: Fork PR Security -- Running Untrusted Code with Deploy Credentials

**What goes wrong:** A fork PR triggers a "plan" workflow that has access to AWS credentials (OIDC or secrets). The fork PR contains malicious code that exfiltrates credentials during the build/plan step, even though "apply" was never triggered.

**Why it happens:** GitHub's `pull_request` event from forks runs with read-only permissions and no access to secrets. But `pull_request_target` runs in the base repo's context with full secret access. If the workflow uses `pull_request_target` and checks out the fork's code (a "pwn request"), the fork's code runs with the base repo's credentials. The November 2025 "Shai Hulud v2" worm [exploited exactly this pattern](https://orca.security/resources/blog/pull-request-nightmare-part-2-exploits/) to infect 20,000+ repositories.

**Consequences:** AWS credential exfiltration. The attacker gets a temporary OIDC token or actual AWS credentials. They can deploy malicious Lambda functions, steal data, or destroy infrastructure.

**Prevention:**
- **Never use `pull_request_target` for Ferry workflows.** Ferry does not need it. The plan can run via the backend Lambda (which receives the webhook, does the diff analysis server-side, and posts a Check Run) without executing any user code.
- **Plan does NOT build containers for fork PRs.** The "plan" for a PR should be purely analytical (diff files, match resources, show what would be affected). It should NOT run `docker build` or any user code. Building is only for apply (post-merge or authorized deploy).
- **For same-repo PRs (non-fork):** The `pull_request` event is safe for plan-only operations since secrets are available. But still avoid running untrusted code paths during plan.
- **GitHub's December 2025 changes** (effective 12/8/2025) tightened `pull_request_target` behavior: the workflow file is always sourced from the default branch, and environment branch protection rules now evaluate against `refs/pull/number/merge` for PR events. This helps but does not eliminate the risk if the checkout step explicitly fetches the fork's code.
- Ferry's architecture (backend does analysis, action does execution) naturally provides this separation -- plan analysis happens in the trusted Lambda, not in GHA runners.

**Detection:** Open a fork PR that adds `echo $AWS_SECRET_ACCESS_KEY` to a build step. If the workflow runs and the secret is exposed, you have a pwn request vulnerability.

**Confidence:** HIGH -- verified from [GitHub Security Lab](https://securitylab.github.com/resources/github-actions-new-patterns-and-mitigations/), [Orca Security research](https://orca.security/resources/blog/pull-request-nightmare-part-2-exploits/), and [GitHub changelog (2025-11-07)](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/).

**Phase:** Must be addressed in the architecture/design phase. The plan vs apply security boundary is a foundational decision.

---

### Pitfall 7: Environment Branch Protection Rules Break PR Deploys (December 2025 Changes)

**What goes wrong:** You configure a GitHub Environment `staging` with a branch protection rule allowing only `main`. You expect PR-triggered deploys to `staging` to work (since the PR will merge to main). But the deploy job hangs or fails because the environment branch rule evaluates against `refs/pull/{number}/merge` (the PR merge ref), not the target branch.

**Why it happens:** As of December 8, 2025, GitHub changed how environment branch protection rules evaluate for pull request events. For `pull_request` family events, the rule now evaluates against `refs/pull/number/merge` -- the merge commit ref. A branch pattern like `main` does not match `refs/pull/42/merge`. This change was made for security reasons ([GitHub changelog 2025-11-07](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/)).

**Consequences:** PR-triggered environment deploys silently fail to match branch protection rules. The job either skips, fails, or never starts. If you designed the environment mapping around the old behavior (pre-December 2025), all PR deploys break.

**Prevention:**
- **Add `refs/pull/*` or `refs/pull/*/merge` patterns** to environment branch protection rules for environments that should be accessible from PR workflows.
- **However:** For Ferry's model, PR "plan" should NOT deploy to any environment -- it is purely analytical. Only "apply" (triggered after merge or via explicit command) should target environments. This means Ferry can avoid this pitfall entirely by not referencing `environment:` in PR plan workflows.
- **If mid-way deploys are needed** (deploy PR to staging before merge): the deploy must use `workflow_dispatch` triggered by the backend, not `pull_request` triggers. `workflow_dispatch` always runs on the default branch, so environment rules evaluate against the default branch ref -- which matches `main` patterns.
- Document this GHA behavioral change prominently -- users who set up GitHub Environments before December 2025 may have stale branch patterns.

**Detection:** Try to deploy to a protected environment from a PR workflow. If the job hangs waiting for approval or fails with "branch not allowed," the branch pattern does not match the PR merge ref.

**Confidence:** HIGH -- directly from [GitHub changelog (2025-11-07)](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/) and [community discussion #182312](https://github.com/orgs/community/discussions/182312).

**Phase:** Must be addressed in the environment mapping design phase.

## Moderate Pitfalls

### Pitfall 8: Duplicate Events -- PR Merge Triggers Both `push` and `pull_request`

**What goes wrong:** When a PR is merged to main, GitHub fires both a `push` event (code landed on main) and a `pull_request` event (PR closed with merge). If the backend handles both, you get duplicate deploys -- one from the push handler and one from the PR merge handler. Alternatively, the push handler deploys while the PR handler tries to run "apply" simultaneously.

**Why it happens:** A PR merge is both a push (code arrives on the target branch) and a PR state change (merged=true). GitHub fires both events for the same commit. The existing dedup mechanism (`is_duplicate` in `dedup.py`) keys on `delivery_id`, but these are different deliveries for different events on the same commit.

**Consequences:** Double deploy attempts. At best, the second one is a no-op (content hash unchanged). At worst, you get concurrent Lambda updates racing each other, or double Check Run posts confusing the user.

**Prevention:**
- **Dedup by commit SHA + event type, not just delivery ID.** Add `(sha, "deploy")` to the dedup table when a push-triggered deploy fires. When the PR merge handler processes the same SHA, check for existing deploy dedup entry and skip.
- **Alternative (simpler):** Keep push as the only deploy trigger for default branch merges. The PR `closed`+`merged` event only updates the PR status (e.g., marks the Check Run as "applied"). Do not trigger deploys from PR merge events.
- This aligns with Ferry's current architecture: push to default branch triggers dispatch. The PR event just needs to update status, not trigger a second deploy.
- [GitHub community discussion #26940](https://github.com/orgs/community/discussions/26940) documents this duplicate event pattern extensively.

**Detection:** Merge a PR and check the Actions tab. If two workflow runs fire for the same commit, you have a duplicate event problem.

**Confidence:** HIGH -- documented GHA behavior, directly observable.

**Phase:** Backend event handler design. Decide the "who triggers deploy" contract up front.

---

### Pitfall 9: Environment Mapping Complexity Explosion

**What goes wrong:** You design the environment mapping system to support flexible patterns: "PRs deploy to staging," "main deploys to production," "release/* branches deploy to staging." The ferry.yaml config grows complex:
```yaml
environments:
  staging:
    branches: ["develop", "feature/*", "pr-*"]
    aws_role_arn: "arn:aws:iam::role/staging"
  production:
    branches: ["main", "release/*"]
    aws_role_arn: "arn:aws:iam::role/production"
```
Users misconfigure patterns, environments overlap for the same branch, and the backend needs complex glob matching logic.

**Why it happens:** The impulse to support every possible branching strategy leads to a generic pattern-matching system. But most serverless teams have exactly two environments (staging + production) with exactly two patterns (PRs -> staging, main -> production). Over-engineering the mapping creates config validation complexity, user confusion, and edge cases (what if a branch matches both staging and production patterns?).

**Consequences:** User confusion ("which environment did this deploy to?"), silent misrouting (deploys go to wrong environment), and ongoing bug reports from edge-case pattern matching.

**Prevention:**
- **Start with exactly two hardcoded patterns:** PRs -> staging, default branch -> production. No glob matching, no custom patterns, no user-configurable branch lists.
- **Use ferry.yaml to specify environment NAMES and role ARNs, not branch patterns:**
  ```yaml
  environments:
    staging:
      aws_role_arn: "arn:aws:iam::role/staging"
    production:
      aws_role_arn: "arn:aws:iam::role/production"
  ```
  The backend determines which environment based on event type (PR push -> staging, default branch push -> production), not user-configured branch patterns.
- **Defer custom branch patterns to v3+.** If users genuinely need `release/*` -> staging, add it later with evidence of real demand.
- Atlantis's lesson: their `when_modified` patterns and workspace mapping are a frequent source of user confusion and support requests. Simpler is better for v1.

**Detection:** Ask a new user to configure environment mapping. If they need more than 60 seconds to understand which environment their PR will deploy to, the mapping is too complex.

**Confidence:** MEDIUM -- based on Atlantis/Digger ecosystem patterns and product design principles.

**Phase:** Environment mapping design phase. Make the simple choice first.

---

### Pitfall 10: Workflow Template Complexity Explosion (Environments x Types x Modes)

**What goes wrong:** The unified workflow template needs to handle:
- 3 resource types (lambda, step_function, api_gateway)
- 2 modes (plan, apply)
- 2+ environments (staging, production)

Naive approach: 3 x 2 x 2 = 12 job definitions in the workflow YAML. The file becomes 500+ lines, unmaintainable, and impossible for users to understand.

**Why it happens:** GHA does not support dynamic job creation. Every job must be statically defined. If you need per-environment AND per-type AND per-mode jobs, the combinatorial explosion requires either massive YAML or a fundamentally different approach.

**Consequences:** Users cannot understand or maintain their workflow file. Bugs in one job do not get fixed in the other 11 copies. Template updates require touching every job.

**Prevention:**
- **Plan does NOT run in GHA.** Ferry's plan is a Check Run posted by the backend Lambda. No workflow job needed for plan. This eliminates the "mode" dimension entirely: workflow only handles "apply" (deploy). The matrix is 3 types x 1 mode = 3 jobs (same as v1.x).
- **Environment is a parameter, not a job dimension.** Each deploy job receives the environment name and role ARN from the setup action output. The same `deploy-lambda` job handles both staging and production deploys -- the environment just changes the AWS role ARN and the `environment:` field on the job.
  ```yaml
  deploy-lambda:
    environment: ${{ needs.setup.outputs.environment }}
    # ... same steps, different role ARN from payload
  ```
- **If you must have separate environment jobs** (e.g., for different approval workflows), use reusable workflows (`workflow_call`) to avoid duplication. Define deploy-lambda once, call it with different environment parameters.
- Keep the user-facing template to the same 4-job structure as v1.5 (setup + 3 deploy types). Environment is an input to the deploy, not a multiplier of jobs.

**Detection:** Count the jobs in the workflow YAML. If it exceeds 6-7, the template is too complex.

**Confidence:** HIGH -- direct analysis of GHA constraints plus v1.4/v1.5 template evolution.

**Phase:** Workflow template design phase. Architecture decision that must be made before template implementation.

---

### Pitfall 11: PR Events Fire for Every Push to PR Branch

**What goes wrong:** The backend subscribes to `pull_request` events for plan functionality. Every push to a PR branch fires a `pull_request.synchronize` event. For an active PR with 20+ pushes, the backend runs plan 20+ times, creating 20+ Check Runs, 20+ PR comments, or 20+ dispatch events. API rate limits hit, PR comment thread becomes unreadable, and GHA runner minutes burn.

**Why it happens:** GitHub fires `pull_request.synchronize` on every push to a PR branch. The backend processes each event independently. Without rate limiting or dedup by PR (not by delivery), each push generates a full plan cycle.

**Consequences:** GitHub API rate limit exhaustion (especially for the GitHub App installation token, which has 5,000 requests/hour). PR timeline flooded with plan updates. Unnecessary GHA runner usage if plans trigger dispatches.

**Prevention:**
- **Debounce plan execution.** When a `pull_request.synchronize` event arrives, check DynamoDB for a recent plan on the same PR. If one was created in the last N seconds (e.g., 30s), skip this event. The next push will re-trigger.
- **Update existing Check Run instead of creating new ones.** Use the Check Run update API (`PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}`) to update the existing "Ferry: Deployment Plan" Check Run with the new plan, rather than creating a new one per push.
- **Collapse Check Run comments.** If posting PR comments for plans, edit the existing Ferry comment instead of creating new ones. Use a marker (e.g., `<!-- ferry-plan -->`) to find and update the existing comment.
- The current `create_check_run` function in `runs.py` always creates a new Check Run. This must be changed to "find and update" for PR plan events.

**Detection:** Push 5 commits rapidly to a PR branch. Check the PR timeline -- if there are 5 separate Check Runs or 5 separate comments, debounce is missing.

**Confidence:** HIGH -- direct analysis of `handler.py` event processing and GitHub event documentation.

**Phase:** PR event handling phase. Must be addressed when adding `pull_request` event support.

---

### Pitfall 12: `workflow_dispatch` Environment Secrets Require Explicit `environment:` on Job

**What goes wrong:** You configure GitHub Environment `production` with secrets (e.g., `AWS_ROLE_ARN`). The workflow is triggered via `workflow_dispatch` (Ferry's model). You reference `${{ secrets.AWS_ROLE_ARN }}` in a deploy job, but the secret is empty/undefined because the job does not have an `environment:` field.

**Why it happens:** GitHub Environment secrets are only available to jobs that explicitly reference the environment via the `environment:` field. The workflow-level `secrets` context only contains repository-level secrets, not environment secrets. This is true regardless of how the workflow was triggered (`push`, `workflow_dispatch`, etc.).

**Consequences:** Deploy fails because the role ARN is empty. The error may be cryptic (empty string passed to `configure-aws-credentials`, which fails with "role ARN must be specified").

**Prevention:**
- Every deploy job must include `environment:` referencing the correct GitHub Environment:
  ```yaml
  deploy-lambda:
    environment: ${{ needs.setup.outputs.environment }}
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}  # from environment
  ```
- The setup action must output the environment name so deploy jobs can reference it dynamically.
- If the user has NOT configured GitHub Environments (v1.x migration), the `environment:` field can be omitted and repo-level secrets work as before. But this means the workflow template must conditionally include `environment:` -- which GHA does not support at the job level. Use separate workflow templates for "with environments" and "without environments," or always require environments.

**Detection:** Deploy with environment secrets configured. If `secrets.AWS_ROLE_ARN` is empty in the GHA logs (shown as `***` if set, absent if not), the environment reference is missing.

**Confidence:** HIGH -- standard GitHub documentation on [environment secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions).

**Phase:** Workflow template design phase, when adding environment support.

## Minor Pitfalls

### Pitfall 13: PR Plan Shows "No Changes" When Branch Is Behind Main

**What goes wrong:** A PR was opened days ago. Since then, other PRs have been merged to main that touch the same resources. The plan for this PR shows "no changes" because it compares the PR branch against the current main, and the resource's source_dir was already modified on main. The user thinks their changes will not trigger a deploy, but after merge the push event will detect changes.

**Why it happens:** The change detection logic in `get_changed_files` uses the Compare API (`base...head`). For PR branches, the base is `default_branch` (three-dot compare using merge-base). If main has moved forward and already includes changes to the same files, the three-dot diff may be empty for those files. This is technically correct (the PR is not adding new changes to those files) but confusing from the user's perspective.

**Prevention:**
- Document clearly: "The plan shows changes YOUR PR introduces, not all changes that will deploy. Resources modified by other merged PRs will deploy when your PR merges, even if not shown in this plan."
- Consider showing both: "Resources changed by this PR" + "Resources that will deploy on merge" (the latter includes any resources changed on main since the PR branched).

**Confidence:** MEDIUM -- based on analysis of the existing `compare_base` logic in `handler.py` lines 166-167.

**Phase:** Plan output formatting phase.

---

### Pitfall 14: Check Run Status Does Not Block Merge

**What goes wrong:** The Ferry plan creates a Check Run, but it is not configured as a required status check in the repo's branch protection rules. Users merge PRs without looking at the plan. The plan/apply workflow provides no value because nobody is forced to review it.

**Why it happens:** Creating a Check Run does not automatically make it required. Branch protection rules must be manually configured to require the "Ferry: Deployment Plan" check. New Ferry users skip this setup step, and the plan is just an informational decoration.

**Prevention:**
- Document setup steps explicitly: "Go to Settings > Branches > Branch protection rules > Require status checks > Add 'Ferry: Deployment Plan'."
- Consider using a bot comment instead of (or in addition to) a Check Run, since comments are more visible in the PR timeline.
- The Check Run name must be stable ("Ferry: Deployment Plan") so branch protection rules do not break when Check Run content changes.
- Note: if the Check Run name changes between versions (e.g., from "Ferry: Deployment Plan" to "Ferry Plan"), the required status check breaks and PRs cannot be merged. Choose the name carefully in v2.0 and commit to it.

**Confidence:** HIGH -- standard GitHub feature, but commonly missed setup step.

**Phase:** Documentation and onboarding phase.

---

### Pitfall 15: Concurrent Plans and Applies on Same PR Race

**What goes wrong:** Developer A runs `/ferry apply` while Developer B simultaneously pushes a new commit to the PR. The apply dispatch fires with the old SHA, the new push triggers a plan with the new SHA. The deploy uses old code, the plan shows new code. The PR now shows a plan for code that was not deployed.

**Why it happens:** No locking mechanism on the PR. Multiple events (comment + push) can arrive within milliseconds of each other. The backend processes them independently in separate Lambda invocations.

**Prevention:**
- **Optimistic locking with DynamoDB.** When an apply starts, write a lock record `{pr_number, sha, status: "applying"}`. When a plan event arrives for the same PR, check for an active apply lock. If found, either: (a) skip the plan and post "Deploy in progress, plan deferred," or (b) run the plan but mark the apply as stale.
- **Simpler alternative for v2.0:** Do not support mid-PR deploys. Plan runs on every push. Apply only runs on merge (push to default branch). This eliminates the race entirely because plan and apply never overlap for the same PR.
- Digger's approach: [per-project locks in DynamoDB](https://blog.digger.dev/atlantis-workflow-without-a-backend/) prevent concurrent operations on the same project.

**Detection:** Rapidly push + comment `/ferry apply` on the same PR. Check if both operations complete without interference.

**Confidence:** MEDIUM -- theoretical race condition, but real in high-activity repos.

**Phase:** Plan/apply state management phase, if mid-PR deploys are supported.

---

### Pitfall 16: `pull_request` Events from Forks Have Different Payload Structure

**What goes wrong:** The backend parses `payload["pull_request"]["head"]["sha"]` for the PR's commit SHA. For fork PRs, `payload["pull_request"]["head"]["repo"]["full_name"]` is different from the base repo. If the backend uses this to fetch config or changed files, it accesses the fork repo instead of the base repo, potentially failing with 404 (private fork) or fetching untrusted config.

**Why it happens:** Fork PRs have a different `head.repo` than the base repo. The payload structure is the same, but the values differ. Code that assumes `head.repo == base.repo` silently breaks on fork PRs.

**Prevention:**
- Always use `payload["pull_request"]["base"]["repo"]["full_name"]` for the repo when fetching config and determining dispatch targets.
- Use `payload["pull_request"]["head"]["sha"]` for the commit to analyze, but fetch it from the base repo's context (GitHub makes the PR commits available in the base repo via `refs/pull/{number}/head`).
- For v2.0 initial implementation: explicitly skip fork PRs with a clear message ("Ferry does not support fork PRs in this version"). Add fork PR support later when the security model is proven.

**Detection:** Open a fork PR and verify the plan does not crash or access the wrong repo.

**Confidence:** MEDIUM -- standard GitHub API behavior, but easy to overlook in initial implementation.

**Phase:** PR event handling phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Backend: event handler redesign | Breaking push-to-deploy flow (Pitfall 4) | Isolate event handlers; regression tests for push flow |
| Backend: PR event handling | `issue_comment` runs on wrong branch (Pitfall 2) | Backend dispatches with correct SHA; no direct `issue_comment` workflows |
| Backend: PR event handling | Anyone can trigger apply (Pitfall 3) | Permission check via GitHub collaborator API |
| Backend: PR event handling | Fork PR payload differences (Pitfall 16) | Always use `base.repo` for config; skip fork PRs in v2.0 |
| Backend: PR event handling | Duplicate events on merge (Pitfall 8) | Push is the only deploy trigger for default branch |
| Backend: plan debounce | PR push spam creates excessive plans (Pitfall 11) | Debounce by PR; update existing Check Run |
| Plan/apply state | Stale plan applied after new commits (Pitfall 5) | SHA-bind plans; auto-invalidate on new push |
| Plan/apply state | Concurrent plan and apply race (Pitfall 15) | DynamoDB locking or defer mid-PR deploys to v3 |
| IAM/Infrastructure | OIDC sub claim changes with environments (Pitfall 1) | Update trust policies BEFORE adding environments to workflow |
| Environment mapping | Complexity explosion from flexible patterns (Pitfall 9) | Two hardcoded patterns: PR -> staging, main -> production |
| Workflow template | Combinatorial explosion (types x modes x envs) (Pitfall 10) | Plan is server-side; environment is a parameter, not a job dimension |
| Workflow template | Environment secrets require `environment:` field (Pitfall 12) | Every deploy job must reference environment dynamically |
| Workflow template | Environment branch rules break PR deploys (Pitfall 7) | Use `workflow_dispatch` for deploys, not `pull_request` triggers |
| Security | Fork PRs exfiltrate credentials (Pitfall 6) | Plan is server-side analysis only; no user code execution during plan |
| Documentation | Check Run not required for merge (Pitfall 14) | Document branch protection setup; choose stable Check Run name |
| Plan output | Confusing "no changes" for behind branches (Pitfall 13) | Document behavior; consider showing merge-time impact |

## Integration-Specific Warnings (v1.x -> v2.0 Migration)

These pitfalls are specific to adding PR support to an existing push-to-deploy system rather than building from scratch.

| Concern | Risk | Mitigation |
|---------|------|------------|
| Existing push handler modification | HIGH | Factor into isolated handler functions; push path unchanged in first PR phase |
| IAM trust policy update | HIGH | Must happen before workflow gets `environment:` field; document exact JSON |
| ferry.yaml schema extension | MEDIUM | New `environments` section must be optional (backward compat with v1.x configs) |
| Check Run name stability | MEDIUM | Current name "Ferry: Deployment Plan" must not change if users have it as required check |
| DynamoDB table schema extension | LOW | New fields for plan state/SHA tracking; additive, no migration needed |
| Dispatch payload v3 | MEDIUM | Plan/apply mode field added to `BatchedDispatchPayload`; version-aware parsing already exists from v1.5 |
| User workflow template migration | HIGH | v1.x users need a new workflow template with environment support; provide automated migration or clear upgrade guide |

## Sources

### Primary (HIGH confidence)
- [GitHub OIDC reference: subject claim formats](https://docs.github.com/actions/reference/openid-connect-reference) -- sub claim changes with environment vs branch
- [GitHub changelog: pull_request_target and environment branch protection changes (2025-11-07)](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/) -- December 2025 security changes
- [GitHub Docs: Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) -- environment branch rules, secrets scope
- [GitHub Security Lab: Preventing pwn requests](https://securitylab.github.com/resources/github-actions-new-patterns-and-mitigations/) -- fork PR security patterns
- Ferry codebase: `handler.py`, `trigger.py`, `changes.py`, `runs.py`, `dispatch.py` -- direct analysis of existing code and integration points

### Secondary (MEDIUM confidence)
- [Atlantis: stale plans issue #1122](https://github.com/runatlantis/atlantis/issues/1122) -- stale plan problem documentation
- [Atlantis: apply picks up stale plans #1624](https://github.com/runatlantis/atlantis/issues/1624) -- real-world stale plan incidents
- [Digger: restrict apply user #577](https://github.com/diggerhq/digger/issues/577) -- permission check gaps in plan/apply tools
- [Digger: the case for apply before merge](https://medium.com/@DiggerHQ/the-case-for-apply-before-merge-bc08a7a9bfea) -- plan/apply workflow tradeoffs
- [aws-actions/configure-aws-credentials#454](https://github.com/aws-actions/configure-aws-credentials/issues/454) -- OIDC sub claim issues with environments
- [GitHub community: issue_comment runs on default branch #59389](https://github.com/orgs/community/discussions/59389) -- issue_comment branch behavior
- [actions/checkout: issue_comment checkout #331](https://github.com/actions/checkout/issues/331) -- workarounds for issue_comment checkout
- [GitHub community: duplicate push/pull_request events #26940](https://github.com/orgs/community/discussions/26940) -- duplicate event handling
- [Orca Security: pull_request_nightmare part 2](https://orca.security/resources/blog/pull-request-nightmare-part-2-exploits/) -- Shai Hulud v2 worm exploiting pull_request_target

### Tertiary (LOW confidence)
- [GitHub community: environment branch protection with PR #182312](https://github.com/orgs/community/discussions/182312) -- post-December 2025 environment rule issues
- [Terramate: apply-before-merge vs apply-after-merge](https://terramate.io/rethinking-iac/mastering-terraform-workflows-apply-before-merge-vs-apply-after-merge/) -- workflow pattern comparison
- [env0: apply-before-merge lightning talk](https://www.env0.com/blog/lightning-talk-apply-before-merge-vs-traditional-continuous-deployment) -- industry perspective on apply timing

---
*Research completed: 2026-03-12*
*Ready for roadmap: yes*
