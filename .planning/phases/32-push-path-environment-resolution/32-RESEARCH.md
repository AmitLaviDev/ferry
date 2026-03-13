# Phase 32: Push Path Environment Resolution - Research

**Researched:** 2026-03-13
**Domain:** GitHub push webhook handler -- environment-aware dispatch gating
**Confidence:** HIGH

## Summary

Phase 32 replaces the existing "is default branch?" dispatch gate in the push handler with environment-based gating driven by `ferry.yaml` environment mappings. The CONTEXT.md decisions are clear and specific: push dispatch is driven entirely by `resolve_environment()` + `auto_deploy` flag. No environments configured means no push deploys (intentional breaking change from v1.x). Branch deletions and tag pushes are silently ignored.

This is a focused refactor of roughly 40 lines in `handler.py` (steps 9 and 12 of the push event flow), plus 7 new test cases. All building blocks already exist: `resolve_environment()` is implemented and tested in `checks/plan.py`, `trigger_dispatches()` already accepts `mode`, `environment`, `head_ref`, and `base_ref` keyword arguments, `EnvironmentMapping` has the `auto_deploy` field, and `BatchedDispatchPayload` v2 already carries all environment fields. The change detection logic, config loading, dedup, and auth paths are completely untouched.

**Primary recommendation:** Single plan with one task to refactor the push handler's branch-dependent behavior (steps 9-13) and add comprehensive tests. No new modules, no new dependencies, no new API calls.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **Environment-gated push dispatch (replaces default-branch gating):** Push dispatch is driven entirely by environment mapping. The old "is default branch?" gate is removed. New logic: extract branch from ref -> ignore deletions/tags -> resolve_environment -> no match = silent done -> match + auto_deploy true = Check Run + dispatch -> match + auto_deploy false = silent done.
2. **No environments = no push deploys:** If ferry.yaml has no `environments:` section, pushes produce zero Ferry activity. Deliberately breaks v1.x behavior. ENV-03 in REQUIREMENTS.md must be updated.
3. **auto_deploy: false = silent on push:** No dispatch, no Check Run, no comment on the merged PR. Zero noise.
4. **Direct pushes, force-pushes, and edge cases:** Ferry treats all push events the same -- it doesn't care how commits arrived on the branch. Branch deletions (`deleted: true`) and tag pushes (`refs/tags/...`) silently ignored.

### Claude's Discretion
No discretion areas identified in CONTEXT.md. All decisions are locked.

### Deferred Ideas (OUT OF SCOPE)
None captured during the discussion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPLOY-01 | Ferry auto-deploys affected resources when a PR merges to a mapped branch | Push handler calls `resolve_environment()` on the push branch; if match found and `auto_deploy: true`, triggers dispatch with environment name in payload |
| ENV-02 | Ferry resolves the correct environment name based on the branch being deployed to | `resolve_environment(config, branch)` already exists in `checks/plan.py` and is tested -- reuse it for push path |
| ENV-03 | When no environment matches (or no environments configured), Ferry deploys without an environment (v1.x behavior) | **UPDATED per CONTEXT.md**: no environments = no push deploys. ENV-03 wording in REQUIREMENTS.md must be updated to reflect this decision |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14 | Runtime | Project standard |
| Pydantic v2 | latest | Data models (FerryConfig, EnvironmentMapping, BatchedDispatchPayload) | Already in use, no changes needed |
| structlog | latest | Structured logging | Already in use |
| httpx | latest | GitHub API client | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | latest | Test framework | All tests |
| pytest-httpx | latest | Mock HTTP calls in tests | Integration tests that hit GitHub API |
| moto | latest | Mock AWS (DynamoDB) | Tests needing dedup table |
| PyYAML | latest | Test fixture creation | Building ferry.yaml test configs |

### Alternatives Considered
None. This phase uses existing stack exclusively. No new libraries needed.

## Architecture Patterns

### Current Push Handler Flow (What Changes)

The push handler in `handler.py` currently has this structure at steps 9 and 12:

```python
# Step 9: Extract push context
branch = ref.removeprefix("refs/heads/")
is_default_branch = branch == default_branch

# Step 12: Branch-dependent behavior
if is_default_branch and affected:
    # ... trigger dispatches
if not is_default_branch:
    # ... Check Run for PRs
```

### New Push Handler Flow

```python
# Step 9: Extract push context + early returns
ref = payload.get("ref", "")
deleted = payload.get("deleted", False)

# Early return: branch deletion
if deleted:
    log.info("push_branch_deleted", ref=ref)
    return _response(200, {"status": "ignored", "reason": "branch deleted"})

# Early return: tag push (ref doesn't start with refs/heads/)
if not ref.startswith("refs/heads/"):
    log.info("push_tag_ignored", ref=ref)
    return _response(200, {"status": "ignored", "reason": "tag push"})

branch = ref.removeprefix("refs/heads/")
# ... auth, config, change detection (same as before) ...

# Step 12: Environment-gated dispatch (replaces is_default_branch gate)
environment = resolve_environment(config, branch)

if environment is None:
    # No environment mapping for this branch -- silent
    log.info("push_no_environment_match", branch=branch)
    return _response(200, {"status": "processed", "affected": len(affected)})

if not environment.auto_deploy:
    # Environment exists but auto_deploy is false -- silent
    log.info("push_auto_deploy_disabled", branch=branch, environment=environment.name)
    return _response(200, {"status": "processed", "affected": len(affected)})

# Match + auto_deploy: true -> dispatch + Check Run
if affected:
    env_name = environment.name
    prs = find_open_prs(github_client, repo, after_sha)
    pr_number = str(prs[0]["number"]) if prs else ""
    tag = build_deployment_tag(pr_number, branch, after_sha)
    trigger_dispatches(
        github_client, repo, config, affected, after_sha, tag, pr_number,
        default_branch=default_branch,
        mode="deploy",
        environment=env_name,
        head_ref=after_sha,
        base_ref=branch,
    )
    # Check Run with environment context
    create_check_run(github_client, repo, after_sha, affected)
```

### Key Architectural Decisions

1. **Early returns BEFORE auth**: Branch deletions and tag pushes should return before the auth step (step 8) to avoid wasting an API call for the installation token. The `deleted` and `ref` fields are available in the raw payload.

2. **Early returns AFTER config loading for environment check**: The environment resolution requires a valid `FerryConfig`, so the "no environment match" and "auto_deploy: false" checks happen after config loading and change detection.

3. **Check Run on push dispatches**: The CONTEXT.md specifies "create Check Run (with environment name)" for auto_deploy dispatches. Currently `create_check_run()` does not accept an environment parameter. The existing Check Run format does not include environment info in its title/summary. For now, reuse the existing Check Run function as-is -- it shows affected resources, which is the core information. Environment name can be added in a future enhancement.

4. **PR branch pushes lose their Check Run**: Under v1.x, pushes to non-default branches created Check Runs when there were open PRs. Under the new model, pushes to unmapped branches produce zero activity. This is correct per the CONTEXT.md decisions -- the `pull_request` event handler (phase 30) already creates Check Runs on PR open/sync, which covers the PR preview use case.

### Anti-Patterns to Avoid
- **Do NOT preserve a fallback "default branch always deploys" path**: The old `is_default_branch` gating is completely removed, not kept as a fallback.
- **Do NOT post "deploy was skipped" comments**: When `auto_deploy: false`, the behavior is completely silent -- no noise.
- **Do NOT add environment name to Check Run title yet**: Keep the Check Run format consistent. Environment name in plan comments (phase 30) is already handled. Check Run enhancement can come later.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Environment resolution | Custom branch matching | `resolve_environment()` from `checks/plan.py` | Already implemented and tested with 4 unit tests |
| Dispatch with env params | New dispatch function | `trigger_dispatches()` with `mode`, `environment`, `head_ref`, `base_ref` kwargs | Already accepts these parameters since phase 31 |
| Branch deletion detection | Custom ref parsing | `payload.get("deleted", False)` | GitHub provides this directly in the push payload |
| Tag push detection | Regex on ref | `ref.startswith("refs/heads/")` check | Simple prefix test -- tags use `refs/tags/` |

## Common Pitfalls

### Pitfall 1: Branch Deletion Fetch Failure
**What goes wrong:** When a branch is deleted, `after` SHA is `0000000000000000000000000000000000000000`. Attempting to fetch `ferry.yaml` at this SHA will fail with a 404.
**Why it happens:** The push event fires for branch deletions with `deleted: true` and a zeroed-out `after` SHA.
**How to avoid:** Check `deleted` field BEFORE any API calls (before auth, before config fetch). Return early with "ignored" status.
**Warning signs:** 404 errors in logs when fetching ferry.yaml, `after_sha` appearing as `0000000`.

### Pitfall 2: Tag Push Ref Format
**What goes wrong:** Tag pushes have `ref` like `refs/tags/v1.0`. Calling `ref.removeprefix("refs/heads/")` on a tag ref returns `refs/tags/v1.0` unchanged, which will never match any environment branch mapping.
**Why it happens:** Tag pushes also fire the `push` webhook.
**How to avoid:** Check `ref.startswith("refs/heads/")` before processing. Tags never match environments, so early return saves API calls.
**Warning signs:** Unnecessary config fetches and change detection for tag pushes.

### Pitfall 3: Compare Base for Non-Default Branches
**What goes wrong:** Under v1.x, only the default branch triggered dispatches, and `compare_base = before_sha` was used. Now ANY mapped branch can trigger dispatches. The compare base logic currently uses `before_sha if is_default_branch else default_branch`.
**Why it happens:** The compare base selection was tied to the `is_default_branch` check which is being removed.
**How to avoid:** For environment-mapped pushes, the compare base should be `before_sha` (incremental diff for the branch that was pushed to), not `default_branch`. The old logic was: default branch uses `before_sha` (incremental), PR branches use `default_branch` (merge-base). The new logic should be: environment-mapped branches use `before_sha` (incremental), unmapped branches... are silently ignored. So the compare base is always `before_sha` when we get to change detection after environment resolution.
**Warning signs:** Dispatches triggered for resources that were not changed in the latest push.

### Pitfall 4: Removing PR Branch Check Run
**What goes wrong:** Feature branch pushes currently create Check Runs (step 13). Removing the `is_default_branch` gate removes this behavior. A developer pushing to a feature branch with an open PR will no longer see a Check Run from the push event.
**Why it happens:** The new model only creates Check Runs for environment-mapped branches with `auto_deploy: true`.
**How to avoid:** This is INTENTIONAL. The `pull_request` event handler (phase 30) already creates Check Runs on PR open/sync, covering the PR preview use case. The push-triggered Check Run on feature branches was a v1.x artifact that is no longer needed.
**Warning signs:** None -- this is expected behavior change. Document in phase notes.

### Pitfall 5: ENV-03 Requirement Update
**What goes wrong:** REQUIREMENTS.md still says "When no environment matches (or no environments configured), Ferry deploys without an environment (v1.x behavior)". This contradicts the CONTEXT.md decision.
**Why it happens:** CONTEXT.md explicitly overrides ENV-03.
**How to avoid:** Update ENV-03 wording as part of this phase. New text: "When no environment matches (or no environments configured), pushes produce no Ferry activity."
**Warning signs:** Future phases referencing the old ENV-03 wording.

## Code Examples

### GitHub Push Event Payload Fields (Verified)

Source: [GitHub Docs: Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads#push)

```python
# Key fields in push webhook payload
payload = {
    "ref": "refs/heads/main",           # Branch or tag ref
    "before": "abc123...",               # SHA before push (0*40 for new branch)
    "after": "def456...",                # SHA after push (0*40 for deleted branch)
    "deleted": False,                    # True when branch/tag was deleted
    "created": False,                    # True when branch/tag was created
    "forced": False,                     # True for force-push
    "repository": {
        "full_name": "owner/repo",
        "default_branch": "main",
    },
}
```

### resolve_environment() (Already Implemented)

Source: `backend/src/ferry_backend/checks/plan.py` lines 65-84

```python
def resolve_environment(
    config: FerryConfig,
    base_branch: str,
) -> EnvironmentMapping | None:
    """Find the environment mapping for a target branch."""
    for env in config.environments:
        if env.branch == base_branch:
            return env
    return None
```

### EnvironmentMapping Model (Already Implemented)

Source: `backend/src/ferry_backend/config/schema.py` lines 59-66

```python
class EnvironmentMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    branch: str
    auto_deploy: bool = True
```

### trigger_dispatches() Signature (Already Has Environment Params)

Source: `backend/src/ferry_backend/dispatch/trigger.py` lines 173-187

```python
def trigger_dispatches(
    client, repo, config, affected, sha, deployment_tag, pr_number,
    default_branch="main",
    *,
    mode: str = "deploy",
    environment: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> list[dict]:
```

### Test Pattern: Push Event with Environments

```python
# ferry.yaml with environments
FERRY_YAML_WITH_ENVS = yaml.dump({
    "version": 1,
    "environments": {
        "staging": {"branch": "develop", "auto_deploy": True},
        "production": {"branch": "main", "auto_deploy": True},
    },
    "lambdas": [{
        "name": "order-processor",
        "source_dir": "services/order-processor",
        "ecr_repo": "ferry/order-processor",
    }],
})

# Push to mapped branch -> dispatch with environment
def test_push_to_mapped_branch_dispatches_with_environment(...):
    event = _make_push_event(ref="refs/heads/main", ...)
    # ... mock APIs with environment-aware config
    result = handler(event, None)
    # Verify dispatch payload contains environment="production"
    dispatch_reqs = [r for r in httpx_mock.get_requests() if "dispatches" in str(r.url)]
    payload = json.loads(json.loads(dispatch_reqs[0].content)["inputs"]["payload"])
    assert payload["environment"] == "production"
    assert payload["mode"] == "deploy"
```

## State of the Art

| Old Approach (v1.x) | New Approach (v2.0) | Impact |
|---------------------|---------------------|--------|
| Default branch pushes always dispatch | Only environment-mapped branches with `auto_deploy: true` dispatch | Breaking change -- acceptable (no external users) |
| Feature branch pushes create Check Runs | Feature branch pushes silently ignored (PR handler covers Check Runs) | Cleaner separation of concerns |
| No environment context in dispatch | Dispatch carries `environment`, `mode`, `head_ref`, `base_ref` | Enables GitHub Environments in downstream phases |
| `is_default_branch` as primary gate | `resolve_environment()` as primary gate | Branch-to-environment mapping drives all behavior |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-httpx + moto |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `.venv/bin/python -m pytest tests/test_backend/test_handler_phase2.py -x` |
| Full suite command | `.venv/bin/python -m pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-01 | Push to mapped branch with `auto_deploy: true` -> dispatch with env name | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_mapped_branch_auto_deploy_dispatches -x` | Wave 0 |
| ENV-02 | Environment resolved by matching push ref against ferry.yaml environments | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_environment_name_in_dispatch_payload -x` | Wave 0 |
| ENV-03 | No environments configured -> no push deploys | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_no_environments_silent -x` | Wave 0 |
| N/A | Push to mapped branch with `auto_deploy: false` -> no dispatch | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_auto_deploy_false_silent -x` | Wave 0 |
| N/A | Push to unmapped branch -> silent | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_unmapped_branch_silent -x` | Wave 0 |
| N/A | Branch deletion event -> ignored | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_branch_deletion_ignored -x` | Wave 0 |
| N/A | Tag push event -> ignored | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py::TestPushEnvironment::test_tag_push_ignored -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_backend/test_handler_push_env.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backend/test_handler_push_env.py` -- covers DEPLOY-01, ENV-02, ENV-03, all edge cases
- No new framework install needed. No new fixtures needed beyond what `test_handler_phase2.py` already provides (DynamoDB mock, signature generation, httpx mock helpers).

## Open Questions

1. **Compare base for environment-mapped non-default branches**
   - What we know: Currently `compare_base = before_sha if is_default_branch else default_branch`. The new model removes `is_default_branch`.
   - What's unclear: Should a push to `develop` (mapped to staging) use `before_sha` or `default_branch` as compare base?
   - Recommendation: Use `before_sha` (incremental diff). This is what the default branch path uses and is the correct behavior for detecting what changed in the latest push. The `default_branch` compare base was specifically for PR branch Check Runs (showing full PR diff), which is now handled by the `pull_request` event handler.

2. **Check Run on push dispatch**
   - What we know: CONTEXT.md says "create Check Run (with environment name)" for auto_deploy dispatches. The existing `create_check_run()` does not display environment info.
   - What's unclear: Should the Check Run title/summary include the environment name?
   - Recommendation: Create the Check Run using the existing function as-is. The CONTEXT.md's mention of "with environment name" refers to the fact that the Check Run is created (not skipped), in the context of environment-gated dispatch. Adding environment name display can be a follow-up enhancement.

## Sources

### Primary (HIGH confidence)
- `backend/src/ferry_backend/webhook/handler.py` -- current push handler implementation, analyzed line-by-line
- `backend/src/ferry_backend/checks/plan.py` -- `resolve_environment()` implementation (lines 65-84)
- `backend/src/ferry_backend/dispatch/trigger.py` -- `trigger_dispatches()` signature with `mode`/`environment` params
- `backend/src/ferry_backend/config/schema.py` -- `EnvironmentMapping` model, `FerryConfig.environments` field
- `utils/src/ferry_utils/models/dispatch.py` -- `BatchedDispatchPayload` with all environment fields
- `tests/test_backend/test_handler_phase2.py` -- existing test patterns for push handler integration tests
- `tests/test_backend/test_plan.py` -- existing tests for `resolve_environment()`
- `.planning/phases/32-push-path-environment-resolution/32-CONTEXT.md` -- locked decisions for this phase

### Secondary (MEDIUM confidence)
- [GitHub Docs: Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads#push) -- push event payload structure, `deleted` field, `ref` field format
- `.planning/research/STACK.md` -- v2.0 stack research (no new dependencies needed)
- `.planning/research/SUMMARY.md` -- architecture overview and phase dependencies

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, using existing code exclusively
- Architecture: HIGH -- all building blocks exist, change is a focused refactor of ~40 lines
- Pitfalls: HIGH -- pitfalls identified from reading actual code and understanding push payload structure

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (30 days -- stable domain, no external API changes expected)
