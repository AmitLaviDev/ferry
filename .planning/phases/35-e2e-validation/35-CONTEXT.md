# Phase 35 Context: E2E Validation

**Phase Goal:** Full PR lifecycle proven end-to-end in the real test environment.
**Requirements:** Validates all v2.0 requirements
**Created:** 2026-03-13

## Decisions

### 1. SC #5 reworded — negative case instead of backward compat

Original SC #5: "Existing push-to-deploy behavior (no environments configured) still works with the v2.0 codebase."

Phase 32 decided: no environments configured = no push deploys (intentional breaking change, no external users).

**Revised SC #5:** "Push to a branch with no environment mapping produces zero Ferry activity" — validates the environment-gating logic works correctly as a negative case.

### 2. Single environment: `main` → `staging`

Test repo uses one environment mapping:

```yaml
environments:
  staging:
    branch: main
    auto_deploy: true
```

- PR targets `main` → plan comment shows "→ staging"
- `/ferry apply` deploys to `staging`
- Merge auto-deploys to `staging`
- One GitHub Environment to create (`staging`)

**Deferred:** Multi-environment testing (e.g., `develop` → `staging`, `main` → `production`, mixed `auto_deploy` flags) is a separate future phase.

### 3. Verifiable dummy changes — not just "did it trigger"

Each resource gets a change that's provable beyond GHA going green:

| Resource | Change | Verification |
|----------|--------|-------------|
| Lambda (hello-world) | Change response body string (e.g., `"hello from v2.0"`) | Invoke Lambda, see new string |
| Step Function (hello-chain) | Change visible field in definition (e.g., result payload string) | `describe-state-machine` or console |
| API Gateway (hello-chain) | Change visible field in OpenAPI spec (e.g., description or response example) | `get-rest-api` or hit endpoint |

### 4. AWS_ROLE_ARN moves to environment-level secret

Proves GitHub Environment secret injection works by making `AWS_ROLE_ARN` environment-scoped:

- Delete repo-level `AWS_ROLE_ARN` secret from ferry-test-app
- Create `AWS_ROLE_ARN` secret on the `staging` GitHub Environment
- If deploys succeed → environment secrets work (no extra verification steps needed)
- Setup job has NO `environment:` key (doesn't need AWS creds — just parses payload)

### 5. All manual prerequisites are "yell" steps during execution

The following must be done manually during execution, with loud STOP callouts:

1. **GitHub App webhook events:** Enable `pull_request`, `issue_comment`, `workflow_run` in the Ferry GitHub App settings (Permissions & events → Subscribe to events)
2. **Create GitHub Environment:** Create `staging` environment in ferry-test-app repo settings
3. **Move secret:** Delete repo-level `AWS_ROLE_ARN`, create it as `staging` environment secret

These are surfaced as explicit manual gates in the plan — execution pauses until confirmed.

## Prior Decisions (locked from phases 29-34)

- Non-sticky plan comments — each invocation creates a new comment (phase 31)
- Environment-gated push dispatch — `resolve_environment(config, branch)` matches branch to `EnvironmentMapping` (phase 32)
- No environments = no push deploys (phase 32 breaking change)
- Action outputs `mode` and `environment` (phase 33)
- Workflow template with mode guards (`mode == 'deploy'`), `environment:` key on deploy jobs (phase 34)
- `auto_deploy: true` default, push to mapped branch triggers dispatch (phase 32)
- `/ferry apply` creates dispatch with `mode="deploy"` and resolved environment (phase 31)
- Plan mode never dispatches — zero GHA runner minutes (phase 30)
- Phase 28 E2E pattern: deploy ferry first → update test repo → validate

## Code Context

### Repositories

- **Ferry monorepo:** `/Users/amit/Repos/github/ferry` — all phases 29-34 code pushed to `origin/main`, clean
- **Test repo:** `/Users/amit/Repos/github/ferry-test-app` (AmitLaviDev/ferry-test-app)

### Test repo current state (needs updating)

- `ferry.yaml`: v1.5 format, no `environments:` section
- `.github/workflows/ferry.yml`: v1.5 template (no `mode`/`environment` outputs, no mode guards, no `environment:` key)
- Repo-level secret: `AWS_ROLE_ARN`
- No GitHub Environments configured
- Resources: hello-world Lambda, hello-chain SF, hello-chain APGW

### Test repo target state

- `ferry.yaml`: Add `environments:` with `staging: { branch: main, auto_deploy: true }`
- `.github/workflows/ferry.yml`: v2.0 template from `docs/setup.md` (mode/environment outputs, mode guards, environment key, updated run-name)
- `staging` GitHub Environment with `AWS_ROLE_ARN` secret
- Repo-level `AWS_ROLE_ARN` secret deleted
- GitHub App subscribed to `pull_request`, `issue_comment`, `workflow_run` events

### Task sequence (high-level)

1. Verify ferry backend is deployed (self-deploy CI/CD ran for phases 29-34 code)
2. **MANUAL GATES** — webhook events, GitHub Environment, secret migration
3. Update test repo: `ferry.yaml` + `ferry.yml` on `main`
4. Create feature branch with verifiable dummy changes to all 3 resource types
5. Open PR → verify plan comment appears with "→ staging" and all 3 resources listed
6. Comment `/ferry apply` → verify deploy dispatches, all 3 types deploy successfully, verify changes are live
7. Merge PR → verify auto-deploy triggers with environment, verify changes still live
8. Negative test: push to unmapped branch (or remove environments) → verify zero Ferry activity

### Verification commands

- Run list: `gh run list --repo AmitLaviDev/ferry-test-app --limit 5`
- Run details: `gh run view <id> --repo AmitLaviDev/ferry-test-app --json jobs`
- PR comments: `gh api repos/AmitLaviDev/ferry-test-app/issues/<pr>/comments`
- Lambda invoke: `aws lambda invoke --function-name ferry-test-hello-world ...`
- SF describe: `aws stepfunctions describe-state-machine --state-machine-arn ...`
- APGW describe: `aws apigateway get-rest-api --rest-api-id v1h1ch5rqk`
- Self-deploy status: `gh run list --repo AmitLaviDev/ferry --workflow self-deploy.yml --limit 1`

## Updated Success Criteria

1. Opening a PR in ferry-test-app produces a plan preview comment listing affected resources and target environment ("→ staging")
2. Commenting `/ferry apply` on the PR triggers a deploy workflow that successfully builds and deploys to the `staging` environment
3. Merging the PR triggers auto-deploy with `staging` environment name flowing through to the GHA deploy job
4. GitHub Environment secrets are accessible in deploy jobs (proven by `AWS_ROLE_ARN` being environment-scoped and deploys succeeding)
5. Push to a branch with no environment mapping produces zero Ferry activity

## Deferred Ideas

- **Multi-environment E2E testing**: Two environments (`develop` → `staging`, `main` → `production`), mixed `auto_deploy` flags, test `/ferry apply` on `auto_deploy: false` environment. Separate future phase.
- **Negative test for `auto_deploy: false`**: Push to mapped branch with `auto_deploy: false` → silent. Covered by multi-environment phase.
- **>65KB fallback E2E test**: Unit-tested in Phase 26, skip in E2E (same as Phase 28 decision).

---
*Context created: 2026-03-13*
