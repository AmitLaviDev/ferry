# Feature Landscape

**Domain:** AWS IaC deployment for a GitHub App Lambda backend (staging environment)
**Researched:** 2026-02-28
**Milestone:** v1.1 Deploy to Staging

## Table Stakes

Features the infrastructure MUST have for the app to function and be operationally viable. Missing any of these means the Lambda cannot serve webhook traffic.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| S3 State Backend + DynamoDB Lock | Terraform state must be stored remotely with locking for CI/CD; local state breaks team workflows and GHA self-deploy | Low | Bootstrap project -- must be created first, before all other TF projects. Single S3 bucket + DynamoDB lock table. |
| ECR Repository for Ferry Lambda | Container image registry for the backend Lambda; must exist before first push | Low | Single repo (`ferry/backend` or similar). Lifecycle policy to limit stored images (keep last 10-20). |
| Lambda Function (Container Image) | The actual compute resource running the webhook handler | Med | Container image deployment (not zip). 256-512MB memory. 30s timeout sufficient for webhook processing. ARM64 (Graviton) for cost savings. |
| Lambda Function URL (auth_type=NONE) | Webhook endpoint -- GitHub sends POST requests here; GitHub cannot sign AWS IAM requests so NONE auth is mandatory | Low | Auth type MUST be NONE because GitHub webhook delivery has no AWS IAM capability. The app validates via HMAC-SHA256 signature in the handler code itself. CORS not needed (server-to-server). |
| DynamoDB Table for Dedup | Webhook deduplication requires conditional writes; the app code already expects this table | Low | Partition key `pk` (String), sort key `sk` (String). TTL attribute `expires_at`. PAY_PER_REQUEST billing (low, bursty traffic). |
| DynamoDB TTL Enabled | Automatic cleanup of expired dedup records (24h TTL set in app code) | Low | TTL attribute name: `expires_at`. Without this, the table grows forever. DynamoDB TTL deletes are free (no WCU consumed). |
| Secrets Manager Secret(s) | GitHub App credentials (private key, webhook secret, app ID, installation ID) must not be in env vars or code | Med | App reads FERRY_PRIVATE_KEY, FERRY_WEBHOOK_SECRET, FERRY_APP_ID, FERRY_INSTALLATION_ID from env vars (pydantic-settings). Two options: (A) Lambda env vars referencing Secrets Manager via extension, or (B) env vars populated from TF `data.aws_secretsmanager_secret_version`. Option B is simpler for staging. |
| IAM Execution Role | Lambda needs permissions for DynamoDB writes, Secrets Manager reads, CloudWatch Logs, and X-Ray | Med | Least-privilege: dynamodb:PutItem on dedup table, secretsmanager:GetSecretValue on Ferry secret, logs:CreateLogGroup/CreateLogStream/PutLogEvents, xray:PutTraceSegments/PutTelemetryRecords. |
| CloudWatch Log Group | Lambda logs go here; must configure retention to avoid unbounded cost | Low | `/aws/lambda/ferry-backend`. Set retention to 30 days for staging (not indefinite). The app already uses structlog JSON output compatible with CloudWatch Logs Insights. |
| OIDC Identity Provider + GHA Deploy Role | GitHub Actions needs AWS access to push ECR images and update Lambda; OIDC avoids stored credentials | Med | `aws_iam_openid_connect_provider` for `token.actions.githubusercontent.com`. Trust policy scoped to the specific repo and branch. Role needs ecr:GetAuthorizationToken, ecr:BatchCheckLayerAvailability, ecr:PutImage, ecr:InitiateLayerUpload, ecr:UploadLayerPart, ecr:CompleteLayerUpload, lambda:UpdateFunctionCode. |
| Self-Deploy GHA Workflow | Automated pipeline: on push to main, build container, push to ECR, update Lambda | Med | workflow_dispatch + push trigger. Steps: checkout, configure AWS creds (OIDC), ECR login, docker build+push, aws lambda update-function-code. This is Ferry deploying itself. |
| Backend Dockerfile | Container image for the ferry-backend Lambda package | Low | Based on `public.ecr.aws/lambda/python:3.14`. COPY backend + utils packages, pip install, set CMD to handler. Simpler than the Magic Dockerfile (no build secrets, no system packages needed). |

## Differentiators

Features that improve operational quality but are not strictly required for the app to run. Include these for a production-ready staging environment.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| CloudWatch Alarms (5xx + Latency) | Proactive notification when webhooks fail or slow down; catch issues before users notice | Low | Alarm on Url5xxCount > 0 over 5min, UrlRequestLatency p99 > 5s. SNS topic for email notification. Lambda Function URL exposes these metrics natively per AWS docs. |
| X-Ray Active Tracing | Trace webhook processing end-to-end; identify slow GitHub API calls or DynamoDB latency | Low | `tracing_config { mode = "Active" }` on Lambda + AWSXRayDaemonWriteAccess policy. Adds two trace segments per invocation: service-level and function-level. Sampling: 1 req/sec + 5% additional. |
| Lambda Reserved Concurrency | Rate-limit the Lambda to prevent runaway costs or accidental DynamoDB throttling | Low | Set to 10-25 for staging. RPS limit = 10x reserved concurrency. Returns HTTP 429 when exceeded (GitHub retries webhooks). Can set to 0 for emergency deactivation. |
| Lambda Alias (live) | Decouple the "current version" from $LATEST; enables future blue/green or canary deploys | Low | Create a `live` alias pointing to $LATEST. Function URL attached to alias, not to $LATEST directly. Self-deploy workflow publishes new version + updates alias. |
| CloudWatch Dashboard | Single-pane view of Lambda metrics, DynamoDB metrics, error rates | Low | Widgets: invocation count, error count, duration p50/p99, DynamoDB consumed capacity, throttle count. Quick operational visibility without digging through metrics. |
| Terraform Variable Separation (tfvars) | Environment-specific values in `.tfvars` files; same TF code for staging and prod | Low | `staging.tfvars` and future `prod.tfvars`. Variables: environment, lambda_memory, log_retention_days, reserved_concurrency. Enables prod environment later without duplicating TF code. |
| DynamoDB Point-in-Time Recovery | Protects dedup table against accidental deletes; AWS best practice for any production table | Low | `point_in_time_recovery { enabled = true }`. Negligible cost. Not critical for a dedup table (data is ephemeral) but good hygiene. |
| Resource Tagging Strategy | Consistent tags across all resources for cost tracking and organization | Low | Tags: Project=ferry, Environment=staging, ManagedBy=terraform. Applied via `default_tags` in provider block. |

## Anti-Features

Features to explicitly NOT build for v1.1 staging deployment.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| API Gateway in front of Function URL | Adds complexity, cost, and another failure point. Function URL already provides HTTPS endpoint. GitHub webhooks do not need API keys, rate limiting, or request transformation. | Use Lambda Function URL directly with auth_type=NONE. The app handles HMAC validation internally. |
| WAF / CloudFront in front of Lambda | Overkill for a webhook endpoint that validates signatures itself. Adds latency and cost. GitHub IPs change frequently -- IP allowlisting is fragile. | HMAC-SHA256 signature validation in the handler is the security boundary. Invalid signatures get 401 before any processing. |
| VPC Configuration for Lambda | Lambda does not need VPC access. It talks to DynamoDB (public endpoint), GitHub API (public), and Secrets Manager (public). VPC adds cold start latency (1-2s) and requires NAT Gateway ($32+/month). | Keep Lambda in default (no VPC) configuration. All services accessed via public endpoints. |
| Custom Domain for Function URL | Unnecessary for staging. GitHub App webhook URL is configured once and does not need to be pretty. Adds ACM certificate and Route53 complexity. | Use the auto-generated Function URL (`*.lambda-url.*.on.aws`). Add custom domain for prod only if needed. |
| Multi-environment Terraform Workspaces | Terraform workspaces add state management complexity. The ConvergeBio/iac-tf pattern uses directory-based environment separation, not workspaces. | Use directory structure: `teams/platform/aws/staging/` vs future `teams/platform/aws/prod/`. One state file per directory. |
| Secrets Manager Rotation | Rotation adds Lambda + rotation schedule complexity. GitHub App credentials do not expire on their own -- only rotated manually when compromised. | Store secrets statically in Secrets Manager. Rotate manually if needed. |
| Lambda Provisioned Concurrency | Eliminates cold starts but costs money 24/7. Webhook latency tolerance is high (GitHub allows 10s timeout). Cold starts on container Lambdas are 1-3s -- acceptable for staging. | Accept cold starts. GitHub retries on timeout. Revisit for prod if needed. |
| Terraform Modules (reusable) | Premature abstraction. Ferry has exactly one Lambda, one DynamoDB table, one Function URL. Writing a module for a single use adds indirection without reuse. | Inline resource definitions in the TF project files. Extract modules only when a second environment reveals genuine duplication. |
| KMS Customer Managed Key | Default AWS-managed encryption is sufficient for staging. CMK adds key management overhead and $1/month per key. | Use default encryption for DynamoDB, CloudWatch Logs, Secrets Manager. Revisit for prod if compliance requires it. |
| Lambda Layers | The backend has modest dependencies (httpx, pydantic, boto3, structlog, PyJWT). Container image deployment bundles everything. Layers add deployment complexity for no benefit with container images. | Ship everything in the container image. Layers are for zip-based deployments, not container Lambdas. |
| Lambda Dead Letter Queue (DLQ) | Function URL invocations are synchronous -- errors return directly to GitHub as HTTP responses. DLQ only applies to async invocations, which Ferry does not use. | Not applicable. If async invocations are added later, revisit then. |

## Feature Dependencies

```
S3 State Backend (bootstrap)
  --> ALL other Terraform projects depend on this

ECR Repository
  --> Backend Dockerfile (needs repo to push to)
    --> Self-Deploy GHA Workflow (builds and pushes image)
      --> Lambda Function (needs image in ECR)

OIDC Provider + GHA Role
  --> Self-Deploy GHA Workflow (needs AWS credentials)

Secrets Manager Secret
  --> Lambda Function (env vars reference secret values)
    --> Lambda Function URL (endpoint for webhooks)

DynamoDB Table
  --> Lambda Function (dedup writes)

IAM Execution Role
  --> Lambda Function (assumes this role)

CloudWatch Log Group
  --> Lambda Function (writes logs here)

CloudWatch Alarms --> CloudWatch Log Group + Lambda Function URL (needs metrics)
X-Ray Tracing --> IAM Execution Role (needs xray permissions)
CloudWatch Dashboard --> Lambda Function + DynamoDB Table (aggregates their metrics)
```

**Critical path:** S3 Backend --> ECR Repo --> Dockerfile --> OIDC + GHA Role --> Self-Deploy Workflow --> Lambda + DynamoDB + Secrets + IAM + Function URL

## MVP Recommendation

### Phase 1: Bootstrap (must be first, manual `terraform apply` from local machine)
1. S3 state backend + DynamoDB lock table
2. ECR repository for ferry-backend

### Phase 2: Shared Resources (can also be local apply)
3. OIDC identity provider for GitHub Actions
4. GHA deploy role (ECR push + Lambda update permissions)
5. Secrets Manager secret (placeholder -- values filled manually after GitHub App registration)

### Phase 3: Core Infrastructure (target for self-deploy)
6. IAM execution role for Lambda
7. DynamoDB dedup table (with TTL enabled)
8. CloudWatch log group (with 30-day retention)
9. Lambda function (container image, referencing ECR + secrets + DynamoDB)
10. Lambda Function URL (auth_type=NONE)
11. Backend Dockerfile
12. Self-deploy GHA workflow

### Phase 4: Operational Readiness (after app is running)
13. Resource tagging strategy (add to all resources via default_tags)
14. CloudWatch alarms (5xx, latency)
15. X-Ray active tracing
16. Reserved concurrency
17. CloudWatch dashboard

**Defer:**
- Lambda alias (`live`): Add when preparing for prod to enable blue/green. Not needed for initial staging.
- DynamoDB PITR: Nice-to-have, add in Phase 4 if time permits.
- tfvars separation: Include from the start if low effort, otherwise add when prod environment is created.

## App Code Dependencies

The Terraform must satisfy these contracts established by the existing Python code.

| App Code Reference | TF Resource Needed | Details |
|-------------------|--------------------|---------|
| `Settings.app_id` (FERRY_APP_ID env var) | Secrets Manager or Lambda env var | GitHub App ID string |
| `Settings.private_key` (FERRY_PRIVATE_KEY env var) | Secrets Manager secret | PEM private key content, stripped whitespace |
| `Settings.webhook_secret` (FERRY_WEBHOOK_SECRET env var) | Secrets Manager secret | HMAC-SHA256 webhook validation secret |
| `Settings.table_name` (FERRY_TABLE_NAME env var) | Lambda env var pointing to DynamoDB table name | Must match the actual DynamoDB table name |
| `Settings.installation_id` (FERRY_INSTALLATION_ID env var) | Secrets Manager or Lambda env var | Integer, GitHub App installation ID |
| `Settings.log_level` (FERRY_LOG_LEVEL env var) | Lambda env var | Default "INFO", set to "DEBUG" for staging |
| `boto3.client("dynamodb", region_name="us-east-1")` | DynamoDB table in us-east-1 | Region is hardcoded in handler.py |
| `structlog.PrintLoggerFactory()` | CloudWatch Logs | JSON lines to stdout, picked up by CloudWatch automatically |
| DynamoDB schema: pk (S), sk (S), expires_at (N) | DynamoDB table with TTL on `expires_at` | Conditional writes using `attribute_not_exists(pk)` |
| Lambda Function URL payload format v2 | Function URL on the Lambda | Handler expects `event.headers`, `event.body`, `event.isBase64Encoded` |
| `handler` function in `ferry_backend.webhook.handler` | Lambda CMD / handler config | Entry point: `ferry_backend.webhook.handler.handler` |

## Secrets Strategy Detail

The app uses `pydantic-settings` with `env_prefix="FERRY_"`, loading all config from environment variables at cold start. Two viable approaches:

**Option A: Direct env vars from Terraform (recommended for staging)**
- Terraform reads secret values via `data.aws_secretsmanager_secret_version`
- Passes values as Lambda environment variables in the `aws_lambda_function` resource
- Pros: Simple, no Lambda extension needed, no code changes
- Cons: Secret values visible in TF state and Lambda console
- Mitigation: TF state is encrypted at rest in S3; Lambda console access restricted by IAM

**Option B: Secrets Manager Lambda Extension**
- Lambda extension layer fetches secrets at cold start
- Requires code changes to read from extension HTTP endpoint instead of env vars
- Pros: Secrets never in env vars or TF state
- Cons: Adds Lambda layer dependency, requires code changes, adds cold start latency
- Verdict: Overkill for staging. Consider for prod if security posture requires it.

**Recommendation: Option A.** Populate FERRY_APP_ID, FERRY_PRIVATE_KEY, FERRY_WEBHOOK_SECRET, FERRY_INSTALLATION_ID as Lambda env vars sourced from Secrets Manager via Terraform data source. Set FERRY_TABLE_NAME and FERRY_LOG_LEVEL as plain env vars (not secrets).

## Sources

- AWS Lambda Function URL configuration: https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html (HIGH confidence)
- AWS Lambda Function URL monitoring/metrics: https://docs.aws.amazon.com/lambda/latest/dg/urls-monitoring.html (HIGH confidence)
- AWS Lambda Function URL invocation format: https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html (HIGH confidence)
- AWS Lambda limits: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html (HIGH confidence)
- AWS Lambda X-Ray tracing: https://docs.aws.amazon.com/lambda/latest/dg/lambda-x-ray.html (HIGH confidence)
- AWS Lambda environment variables best practices: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html (HIGH confidence)
- AWS Secrets Manager Lambda integration: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_lambda.html (HIGH confidence)
- DynamoDB TTL: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html (HIGH confidence)
- Ferry backend handler.py, settings.py, dedup.py: direct code analysis (PRIMARY source)
- ConvergeBio/iac-tf conventions: project memory (MEDIUM confidence)
