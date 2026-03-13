# Project Research Summary

**Project:** Ferry v2.0 — PR Integration (plan/apply model)
**Domain:** GitHub-native PR-ops for serverless AWS deployments
**Researched:** 2026-03-12
**Confidence:** HIGH

## Executive Summary

Ferry v2.0 adds a plan/apply workflow to an already-proven serverless deploy system. The core model mirrors Digger/Atlantis: when a PR is opened or updated, Ferry posts a plan preview (which resources would deploy, to which environment); when a merge or `/ferry apply` command fires, Ferry does the actual deployment. The research confirms this can be implemented with zero new Python dependencies, zero new infrastructure, and zero new GitHub App permissions — all the building blocks already exist. The primary work is routing two new webhook event types (`pull_request`, `issue_comment`) through the existing handler, extending the Pydantic dispatch payload with `mode`/`environment` fields, and wiring `environment:` into the GHA workflow template.

The recommended approach is a pass-through model for GitHub Environments: Ferry resolves which environment name maps to the target branch (using a new `environments:` section in `ferry.yaml`), injects it into the dispatch payload, and the workflow job's `environment:` key handles all secrets/protection rules automatically. Ferry does not call the Environments API and does not manage approval gates — that is GHA's job. The plan preview is posted directly by the backend as a sticky PR comment with a hidden HTML marker, skipping a workflow dispatch entirely for plan mode. This avoids burning GHA runner minutes for what is purely a text preview.

The main risk is backward compatibility. Existing users have `ferry.yml` workflow files that reference v2 payload outputs from the v1.5 batched dispatch milestone. The v2.0 payload bumps to v3, adding four new additive fields. The upgrade path is straightforward: the setup action must output `mode` and `environment` with safe defaults (`"deploy"` and `""`) when receiving a v2 payload, so existing push-based deploys continue working without any user action. The `issue_comment` event handler requires a follow-up GitHub API call to fetch the PR's head SHA — this extra round-trip is unavoidable but is the standard pattern used by every comparable tool including Digger and Atlantis.

## Key Findings

### Recommended Stack

v2.0 requires no new Python libraries. The existing stack (Python 3.14, httpx thin wrapper, PyJWT+cryptography, boto3, Pydantic v2, structlog, DynamoDB, uv workspace) is sufficient for all new functionality. The three new GitHub API calls (fetch PR details, list PR comments, update comment) all use existing `get()`, `post()`, and `patch()` methods on the `GitHubClient`.

See `.planning/research/STACK.md` for full details.

**Core technologies:**
- `httpx` + custom `GitHubClient`: 3 new API endpoints (PR fetch, list comments, update comment) via existing methods — no SDK needed
- `Pydantic v2`: One new model (`EnvironmentMapping`), `FerryConfig` gains `environments: []` field, `BatchedDispatchPayload` bumps to v3 with 4 new fields
- DynamoDB: Existing dedup table handles `pull_request` and `issue_comment` events — no schema change
- GitHub App: 2 new webhook subscriptions (`pull_request`, `issue_comment`); all existing permissions are sufficient

**New GitHub API calls (3 total, all via existing GitHubClient):**
- `GET /repos/{owner}/{repo}/pulls/{number}` — fetch head SHA and branch context after `issue_comment`
- `GET /repos/{owner}/{repo}/issues/{number}/comments?per_page=100` — find existing sticky plan comment
- `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` — update existing sticky plan comment in-place

### Expected Features

The v1.4/v1.5 baseline is shipped and proven: single `ferry.yml` dispatch, batched multi-type payload, per-type matrix jobs with boolean gates. v2.0 features are incremental additions on top. See `.planning/research/FEATURES.md` for the v1.4 feature baseline and `.planning/research/ARCHITECTURE.md` for the v1.5 architecture.

**Must have (table stakes for v2.0):**
- Plan preview comment on every PR open/sync — sticky, updates in-place using `<!-- ferry:plan -->` marker, never creates duplicates
- `/ferry apply` comment command — triggers deploy from PR without merging
- GitHub Environments integration — environment name from `ferry.yaml` flows into workflow job's `environment:` key, enabling environment secrets and protection rules
- Backward compatibility — existing push-based deploys continue working with no changes required from users

**Should have (competitive differentiators):**
- Check Run on PR for plan status (already exists and is reused)
- Clear mode separation in GHA UI — deploy runs show active deploy jobs; plan mode does not dispatch at all
- Auto-deploy on merge — when `auto_deploy: true` (the default), a push to the mapped branch triggers deploy, matching current behavior

**Defer to v3+:**
- Per-environment resource overrides in `ferry.yaml` (environment-specific Lambda aliases, stage names, etc.)
- Branch glob patterns for environment mapping (simple exact-match string is sufficient for v2.0)
- Mid-PR partial deploys (deploy individual resources before full merge)
- Manual approval UI outside of GitHub Environments protection rules

### Architecture Approach

v2.0 extends the batched dispatch architecture from v1.5. The backend handler gains two new routing paths: `pull_request` events trigger plan preview (comment + check run, no dispatch); `issue_comment` events with `/ferry apply` trigger a deploy dispatch with `mode="deploy"`. The existing `push` path is extended to resolve environment name from `ferry.yaml` and pass it in the v3 payload. Plan preview is posted by the backend directly — no workflow dispatch for plan mode. This is the simplest correct design.

See `.planning/research/ARCHITECTURE.md` for the v1.5 architecture baseline that v2.0 extends.

**Major components:**
1. `handler.py` (backend) — route `pull_request` and `issue_comment` events alongside existing `push`; early-exit if not relevant action type
2. `plan.py` (new backend module) — sticky comment logic: list comments, find `<!-- ferry:plan -->` marker, create or update
3. `trigger.py` (backend) — extended to accept `mode` and `environment` params; constructs v3 payload
4. `parse_payload.py` (action) — version-aware parser: v3 payload outputs `mode` and `environment`; v2 payload defaults to `mode="deploy"`, `environment=""`
5. `ferry.yaml` schema — `EnvironmentMapping` model with `name`, `branch`, `auto_deploy: bool`; `FerryConfig.environments: list[EnvironmentMapping] = []`
6. `ferry.yml` template — deploy jobs gain `environment: ${{ needs.setup.outputs.environment }}` and `mode == 'deploy'` guard layered on top of existing boolean type gates

**Key flow distinction:**
- `pull_request` event → plan preview directly from backend (no dispatch, no GHA runner)
- `issue_comment /ferry apply` → resolve environment → dispatch with `mode="deploy"`
- `push` to default branch → resolve environment → dispatch with `mode="deploy"` (existing behavior, now environment-aware)

### Critical Pitfalls

Top risks synthesized from v1.5 pitfall research and v2.0-specific risks identified in STACK.md. See `.planning/research/PITFALLS.md` for the full v1.5 pitfall catalog.

1. **Empty matrix crash from `fromJson` on empty payload** — GHA evaluates `strategy.matrix` before `if:` in some execution paths. The v1.5 boolean gates (`has_lambdas == 'true'`) must be preserved in the v2.0 template. The new `mode == 'deploy'` guard must layer on top of, not replace, the boolean type gates. Prevention: `if: needs.setup.outputs.has_lambdas == 'true' && needs.setup.outputs.mode == 'deploy'`.

2. **`issue_comment` payload lacks PR context** — The `issue_comment` webhook payload does not include the PR head SHA or branch names. It includes only a minimal `issue` object with PR URL links. A follow-up `GET /repos/{owner}/{repo}/pulls/{number}` is required to obtain head SHA and `head.ref`/`base.ref`. Do not attempt to infer SHA from the comment payload.

3. **`issue_comment` fires on issues, not just PRs** — The webhook fires for all issue comments. The handler must check `payload["issue"]["pull_request"]` is truthy (non-null) before treating the event as a PR comment. Failure to check will cause the handler to attempt deploying from unrelated issue comments.

4. **Backward compatibility on payload v3** — Existing `ferry.yml` files reference v2 payload outputs. The setup action must output `mode` and `environment` with defaults when receiving a v2 payload: `mode="deploy"`, `environment=""`. Empty `environment:` on a GHA job is equivalent to no environment specified — confirmed correct GHA behavior.

5. **`environment:` expression context restriction in GHA** — The `environment:` key on a job only supports `github`, `needs`, `strategy`, `matrix`, `vars`, and `inputs` contexts. It does NOT support `steps` context. The environment name must come from `needs.setup.outputs.environment` (setup job output), not from a step within the deploy job itself. This is the correct pattern and is verified.

## Implications for Roadmap

The dependency chain is clear: shared Pydantic models must exist before both the backend handler and the action parser can be written. The `pull_request` and `issue_comment` backend handlers are independent of each other and can be developed in parallel after models are done. The action and workflow template update depend only on the models, not on the backend handler phases.

### Phase 1: Shared Models and Schema Extension

**Rationale:** Both the backend and the action import `BatchedDispatchPayload` and `FerryConfig`. Adding fields to these models unblocks all downstream phases. Pure additive change — no existing behavior is altered.
**Delivers:** `EnvironmentMapping` Pydantic model; `environments: list[EnvironmentMapping] = []` on `FerryConfig`; `BatchedDispatchPayload` v3 with `mode: str = "deploy"`, `environment: str = ""`, `head_ref: str = ""`, `base_ref: str = ""`; updated `__init__.py` re-exports; unit tests for new models.
**Addresses:** ferry.yaml environment mapping (table stakes), payload backward compatibility.
**Avoids:** Breaking existing parse paths — all new fields have defaults; v2 payloads remain valid.

### Phase 2: Backend — PR Event Handler and Plan Comment

**Rationale:** The `pull_request` handler is the simplest new event path. The webhook payload contains everything needed (head SHA, branch names, PR number) without any follow-up API calls. It reuses existing `get_changed_files()`, `match_resources()`, `create_check_run()`, and `post_pr_comment()`. The new `plan.py` module adds sticky comment logic.
**Delivers:** Plan preview comment posted on every PR open/sync; check run status on PR; new `plan.py` module with sticky comment search-and-update logic; dedup for `pull_request` delivery IDs.
**Uses:** Existing change detection and GitHub API wrappers. New: list comments endpoint + update comment endpoint.
**Implements:** `pull_request` routing branch in `handler.py`; `plan.py` (list, find marker, create/update).
**Avoids:** Burning GHA runner minutes on plan previews — backend posts comment directly, no dispatch.

### Phase 3: Backend — Issue Comment Handler and Deploy Dispatch

**Rationale:** Depends on Phase 1 (v3 payload model). Requires a follow-up PR API call for head SHA context. Should come after Phase 2 to validate the plan comment pattern before adding the deploy trigger.
**Delivers:** `/ferry apply` detection; deploy dispatch from PR comment with `mode="deploy"` and resolved environment; dedup for `issue_comment` delivery IDs; audit log entry with comment author.
**Uses:** New `GET /repos/{owner}/{repo}/pulls/{number}` for head SHA + branch context; existing `trigger_dispatch()` extended with mode/environment params.
**Implements:** `issue_comment` routing in `handler.py`; `resolve_environment()` function; `is_pr_comment()` guard.
**Avoids:** Acting on regular issue comments — `payload["issue"]["pull_request"]` truthy check is the canonical gate.

### Phase 4: Backend — Push Path Environment Resolution

**Rationale:** Extends the existing push handler to resolve environment name and pass it in the v3 payload. Low-risk because it is purely additive — push deploys already work; this adds environment context on top. Can run in parallel with Phases 2 and 3.
**Delivers:** Push-triggered deploys now carry environment name; users who add `environments:` to `ferry.yaml` automatically get GitHub Environment secrets and protection rules on merge deploys.
**Implements:** Call to `resolve_environment(base_ref, config)` in the push path; `mode="deploy"` and `environment=resolved_name` in the v3 payload.

### Phase 5: Action — v3 Payload Parsing and Outputs

**Rationale:** Depends only on Phase 1 (v3 payload model). Independent of backend handler phases. The action reads the dispatch payload and outputs GHA step outputs; it has no knowledge of how the backend produced the payload.
**Delivers:** `mode` and `environment` outputs from `action/setup/action.yml`; version-aware `parse_payload.py` (v3 path outputs all fields; v2 path defaults `mode="deploy"`, `environment=""`); updated output declarations in `action.yml`.
**Avoids:** Breaking existing `ferry.yml` files that do not yet have `mode`/`environment` gating — v2 payloads still produce `mode="deploy"` so existing deploy jobs continue running.

### Phase 6: Workflow Template Update and Documentation

**Rationale:** Depends on Phase 5 (finalized setup action output names). User-facing change. This is the phase that surfaces the full v2.0 feature set to users.
**Delivers:** Updated `ferry.yml` template with `environment:` on deploy jobs and `mode == 'deploy'` guard; updated setup job output declarations; updated docs; explicit instructions for adding `pull_request` and `issue_comment` webhook subscriptions to the GitHub App (manual step in App settings UI).
**Avoids:** Empty matrix crash — boolean type gates preserved and combined with `mode` guard in each deploy job's `if:` condition.

### Phase 7: E2E Validation

**Rationale:** Full PR lifecycle must be validated end-to-end: PR open triggers plan comment, `/ferry apply` triggers deploy, push to default branch deploys with environment, GitHub Environment secrets are accessible in deploy job.
**Delivers:** Proven PR integration in `AmitLaviDev/ferry-test-app`; `ferry.yaml` updated with `environments:` section; `ferry.yml` updated to v2.0 template; GitHub App webhook subscriptions activated.

### Phase Ordering Rationale

- Phase 1 is first because both backend and action depend on the updated models.
- Phases 2, 3, and 4 are all backend phases that depend only on Phase 1 and can be developed in parallel. Phase 2 is recommended first because it has no follow-up API calls and validates the plan comment pattern before the apply trigger is added.
- Phase 5 (action) depends only on Phase 1 and can run in parallel with Phases 2-4.
- Phase 6 (template) must follow Phase 5 (needs finalized output names from the action).
- Phase 7 is always last; requires all backend phases deployed and test repo updated.

### Research Flags

Phases with well-documented patterns (skip `research-phase`):
- **Phase 1:** Pydantic v2 model extension — established codebase pattern, no novel decisions
- **Phase 2:** Sticky comment — widely-used pattern (Digger, Terraform Cloud, `marocchino/sticky-pull-request-comment`); API endpoints verified in STACK.md
- **Phase 4:** Push environment resolution — simple `env.branch == base_ref` lookup, no novel architecture
- **Phase 5:** Action output extension — identical pattern to v1.5 batched output addition
- **Phase 6:** Workflow template changes — GHA expression contexts verified in STACK.md research

Phases that warrant targeted planning discussion before coding:
- **Phase 3:** `/ferry apply` command parsing — worth explicitly speccing edge cases before implementation: what if the PR was updated (new commit) after the plan comment? what if the branch has no environment mapping? what if the same user types `/ferry apply` twice? None are unknown territory, but explicit decisions prevent later ambiguity.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against official GitHub docs; codebase analyzed directly; zero new dependencies confirmed; all 3 new API endpoints are stable REST v3 |
| Features | HIGH | v1.4/v1.5 baseline is shipped and proven; v2.0 features are incremental additions; sticky comment and plan/apply patterns are mature in the Digger/Atlantis ecosystem |
| Architecture | HIGH | v1.5 batched dispatch is live; v2.0 extension pattern (new event routing, payload v3) is additive and non-breaking; GHA expression contexts for `environment:` confirmed |
| Pitfalls | HIGH | Pitfalls derived from reading actual codebase and verified GHA platform constraints; v1.5 pitfalls are addressed; v2.0-specific risks are bounded and well-understood |

**Overall confidence:** HIGH

### Gaps to Address

- **`/ferry apply` on stale PR (new commit since plan):** When `/ferry apply` is posted after new commits were pushed to the PR, the deploy uses the current head SHA (fetched fresh from the API), not the SHA from when the plan comment was posted. The plan comment may show a stale resource list. Recommended handling: always deploy from current head SHA (safest); optionally add a warning to the comment if head SHA changed since plan. Flag for Phase 3 planning.

- **Empty `environment:` on GHA job:** If `ferry.yaml` has no `environments:` section, the resolved environment name is `""`. Empty string in `environment:` is confirmed equivalent to not specifying it (no environment used). This should have an explicit unit test in Phase 7 validation.

- **GitHub App webhook subscription is a manual step:** Adding `pull_request` and `issue_comment` to the GitHub App's webhook subscriptions requires manual action in the GitHub App settings UI. This cannot be automated via Terraform. Must be explicitly called out in docs and the Phase 7 runbook.

- **Dedup strategy for `issue_comment`:** GitHub does not retry `issue_comment` webhooks as aggressively as `push` webhooks. The DynamoDB conditional write is conservative but correct. If the same delivery ID appears twice (GitHub retry), the second invocation is dropped. Acceptable behavior — the cost is one extra DynamoDB write attempt.

## Sources

### Primary (HIGH confidence)
- [GitHub Docs: Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads) — `pull_request` and `issue_comment` payload structures; `issue.pull_request` field for PR vs issue distinction
- [GitHub Docs: Contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) — expression contexts available for `jobs.<id>.environment` (verified: supports `needs`, not `steps`)
- [GitHub Docs: Deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) — `environment:` on jobs, secret access, protection rules, empty string behavior
- [GitHub Docs: REST API - Issue comments](https://docs.github.com/en/rest/issues/comments) — list, create, update comment endpoints
- [GitHub Docs: REST API - Pulls](https://docs.github.com/en/rest/pulls/pulls) — fetch PR details endpoint
- [GitHub Docs: Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app) — permission requirements for webhook subscriptions
- Existing codebase: `handler.py`, `trigger.py`, `client.py`, `schema.py`, `dispatch.py`, `parse_payload.py`, `action/setup/action.yml` — analyzed directly

### Secondary (MEDIUM confidence)
- [marocchino/sticky-pull-request-comment](https://github.com/marocchino/sticky-pull-request-comment) — sticky comment pattern using hidden HTML marker `<!-- ferry:plan -->`
- [Digger PR comment UX](https://github.com/diggerhq/digger/pull/1071) — reference plan/apply comment flow
- [GitHub Community Discussion #37686](https://github.com/orgs/community/discussions/37686) — `workflow_dispatch` with environment secrets; passing setup output to job `environment:` key
- [GitHub Actions runner issue #998](https://github.com/actions/runner/issues/998) — dynamic environment name via `needs` expression
- [GHA Community: Empty matrix crash](https://github.com/orgs/community/discussions/27096) — boolean guard pattern for `fromJson` (established in v1.5)
- v1.4 FEATURES.md, v1.5 ARCHITECTURE.md, v1.5 PITFALLS.md — shipped milestone research establishing the baseline

---
*Research completed: 2026-03-12*
*Ready for roadmap: yes*
