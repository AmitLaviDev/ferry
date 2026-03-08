# Ferry v1.2 End-to-End Validation Report

**Date:** 2026-03-08
**Status:** PASSED

## Infrastructure Verified

| Component | Status | Evidence |
|-----------|--------|----------|
| Ferry Lambda | Live | `arn:aws:lambda:us-east-1:050068574410:function:ferry-backend` |
| Ferry Function URL | Live | `https://6dtb47ahdfi4hywuclwhwl7x5q0wizqz.lambda-url.us-east-1.on.aws/` |
| DynamoDB dedup table | Live | `ferry-webhook-dedup` |
| GitHub App | Installed | Installed on `AmitLaviDev/ferry-test-app` |
| Self-deploy pipeline | Working | Ferry repo pushes trigger self-deploy via GHA |
| Test ECR repo | Live | `050068574410.dkr.ecr.us-east-1.amazonaws.com/ferry-test/hello-world` |
| Test Lambda | Live | `arn:aws:lambda:us-east-1:050068574410:function:ferry-test-hello-world` |
| Test OIDC role | Working | `arn:aws:iam::050068574410:role/ferry-test-deploy` |

## E2E Loop Results

### Push 1: Code Change (main.py)

| Step | Result | Evidence |
|------|--------|----------|
| Webhook received | Yes | CloudWatch logs show `webhook_event_received` |
| Changes detected | 1 Lambda (`hello-world`) | `source_dir: lambdas/hello-world` matched |
| Dispatch triggered | Yes | GHA run `22816399024` |
| Build completed | Yes | Magic Dockerfile, ECR push succeeded |
| Deploy completed | Yes | UpdateFunctionCode + PublishVersion + UpdateAlias |
| Lambda invocation | `{"message": "hello from ferry-test-v4"}` | `StatusCode: 200`, `ExecutedVersion: 1` via `live` alias |

- **GHA run:** https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22816399024
- **Duration:** 1m21s

### Push 2: Dependency Change (requirements.txt)

| Step | Result | Evidence |
|------|--------|----------|
| Webhook received | Yes | CloudWatch logs show `webhook_event_received` |
| Changes detected | 1 Lambda (`hello-world`) | `source_dir: lambdas/hello-world` matched |
| Dispatch triggered | Yes | GHA run `22817802455` |
| Build completed | Yes | Full rebuild with new dependency |
| Deploy completed | Yes | Lambda LastModified: `2026-03-08T08:57:03Z` |
| Lambda invocation | Success | Function operational with updated dependencies |

- **GHA run:** https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22817802455
- **Duration:** 1m8s

### No-op Push: README Change

| Step | Result | Evidence |
|------|--------|----------|
| Webhook received | Yes | CloudWatch logs show `webhook_event_received` |
| Changes detected | 0 | README.md does not match any `source_dir` |
| Dispatch triggered | No (correct) | No new GHA run appeared |

## Bugs Found and Fixed

9 bugs discovered and fixed during E2E validation (plans 17-01 and 17-02):

| # | Bug | Symptom | Root Cause | Fix |
|---|-----|---------|-----------|-----|
| 0 | find_open_prs 403 crash | Backend crashes on GitHub API 403 | No status_code guard before .json() | Guard on non-200, return safe default |
| 1 | Ferry repo private | GHA: action not found | Can't ref composite actions from private repos | Made repo public |
| 2 | PEP 668 externally managed | `uv pip install --system` rejected | Ubuntu runner Python is externally managed | Added setup-python@v5 to all actions |
| 3 | Wrong Python version | Package install fails | setup-python defaulted to 3.12, needs >=3.14 | Set python-version: "3.14" |
| 4 | Template expressions in YAML | GHA rejects action.yml | `${{ }}` in input description fields | Removed expressions from descriptions |
| 5 | Dockerfile not found | Build fails finding Dockerfile | `__file__` in site-packages != action dir | Bundled via importlib.resources |
| 6 | ECR login TypeError | docker login crashes | Missing text=True for str input | Added text=True to subprocess.run |
| 7 | Waiter AccessDenied | Deploy hangs then fails | Waiter needs GetFunctionConfiguration | Added permission to deploy IAM policy |
| 8 | Lambda can't pull ECR image | Deploy fails with ECR permission error | Execution role needs ECR pull permissions | Added ECR pull + auth to execution role |
| 9 | ECR repo policy missing service principal | Deploy fails despite IAM permissions | Lambda service needs `lambda.amazonaws.com` in repo policy | Added repository_lambda_read_access_arns |

## Known Limitations

**What v1.2 proved:**
- Single Lambda push-to-deploy on default branch (main)
- Magic Dockerfile build for Python runtime
- OIDC authentication for GHA runners
- Change detection correctly matches/skips resources
- Dependency changes trigger full rebuild
- Repeatability (2 successful deploys)

**What v1.2 did NOT prove (future work):**
- PR event handling (Check Runs, PR comments) -- v2
- Step Functions / API Gateway deploy -- v1.3
- Multi-resource ferry.yaml (only tested single Lambda)
- Multi-tenant / cross-org installations -- v2
- Rollback scenarios
- Private repo dependencies via build secrets
- Non-Python runtimes

## Resource Links

| Resource | Link |
|----------|------|
| Ferry Lambda | `arn:aws:lambda:us-east-1:050068574410:function:ferry-backend` |
| Ferry Function URL | `https://6dtb47ahdfi4hywuclwhwl7x5q0wizqz.lambda-url.us-east-1.on.aws/` |
| Ferry CloudWatch | `/aws/lambda/ferry-backend` |
| DynamoDB table | `ferry-webhook-dedup` |
| Test repo | https://github.com/AmitLaviDev/ferry-test-app |
| Test repo Actions | https://github.com/AmitLaviDev/ferry-test-app/actions |
| Test Lambda | `arn:aws:lambda:us-east-1:050068574410:function:ferry-test-hello-world` |
| Test ECR | `050068574410.dkr.ecr.us-east-1.amazonaws.com/ferry-test/hello-world` |
| Test deploy role | `arn:aws:iam::050068574410:role/ferry-test-deploy` |

---
*Generated: 2026-03-08*
*Milestone: v1.2 End-to-End Validation*
