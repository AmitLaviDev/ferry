# Domain Pitfalls: Deploying Ferry to AWS Staging

**Domain:** Lambda + DynamoDB + Function URL deployment to a new AWS account via Terraform
**Project:** Ferry v1.1 (Deploy to Staging)
**Researched:** 2026-02-28
**Overall confidence:** MEDIUM-HIGH (Terraform S3 backend, Lambda Function URLs, OIDC, and Secrets Manager are mature, well-documented AWS/Terraform patterns; web verification tools unavailable)

---

## Critical Pitfalls

Mistakes that block the deployment entirely, require resource recreation, or create security vulnerabilities.

---

### Pitfall 1: Terraform S3 Backend Bootstrap -- The Chicken-and-Egg Problem

**What goes wrong:** Terraform needs an S3 bucket to store its state, but you want Terraform to manage all your infrastructure. The S3 backend bucket must exist BEFORE `terraform init` can run. If you try to create the bucket with Terraform and also use it as your backend in the same project, `terraform init` fails because the bucket does not exist yet.

**Why it happens:** The `backend "s3"` block is evaluated during `terraform init`, before any resources are planned or created. Terraform must connect to the state backend before it can do anything else. This is a fundamental bootstrapping constraint -- you cannot use Terraform to create its own state backend in a single project.

**Consequences:** If you do not handle this correctly, you end up with either: (a) a manually created bucket that drifts outside of Terraform management, (b) a separate bootstrap Terraform project with LOCAL state that you must never lose, or (c) a broken init that blocks all subsequent work.

**Prevention:**
1. **Use a dedicated bootstrap Terraform project with a local-to-S3 state migration.** Create `iac/global/cloud/aws/backend/` as a minimal Terraform project that creates the S3 bucket (with versioning, encryption, and a DynamoDB lock table if desired). Run it first with local state (`terraform.tfstate` file). Once the bucket exists, add the `backend "s3"` block to the bootstrap project itself and run `terraform init -migrate-state` to move the local state into S3. This is the standard pattern -- the bootstrap project manages itself after the initial migration.
2. **Commit the bootstrap project's `backend "s3"` block from the start, but comment it out.** First apply with local state, then uncomment the backend block and run `terraform init -migrate-state`. This makes the two-step process explicit in the code.
3. **Never delete the bootstrap S3 bucket.** Enable versioning and MFA delete (or at minimum, bucket policy preventing deletion). Losing the state bucket means losing ALL Terraform state. Recovery requires `terraform import` for every resource.
4. **Enable S3 bucket versioning from day one.** If a state file is corrupted, you can recover from a previous version.

**Detection:**
- `terraform init` failing with "S3 bucket does not exist"
- Local `terraform.tfstate` files checked into git (should never happen after migration)
- Bootstrap project without a backend block (still using local state -- migration was forgotten)

**Phase relevance:** The very first step of any Terraform work. Must be done correctly before anything else.

**Confidence:** HIGH -- this is the most well-documented Terraform bootstrap pattern.

---

### Pitfall 2: DynamoDB Lock Table Confusion -- Backend Locking vs Application Table

**What goes wrong:** Terraform S3 backend supports an optional DynamoDB table for state locking (prevents concurrent `terraform apply` from corrupting state). Ferry also needs a DynamoDB table for webhook dedup. These are two completely separate tables with different purposes. Teams frequently confuse them, either: (a) trying to use the lock table for application data, (b) forgetting the lock table entirely and risking state corruption, or (c) creating the lock table in the wrong Terraform project (creating another chicken-and-egg).

**Why it happens:** Both use DynamoDB. The lock table needs a specific schema (`LockID` as the partition key -- this is required by Terraform, not configurable). The application table has a different schema (`pk`/`sk`). Mixing them up or forgetting the lock table is a common mistake when both are in the same AWS account.

**Consequences:** Without a lock table, two concurrent `terraform apply` runs (e.g., from a self-deploy workflow and a manual run) can corrupt the state file. With a misconfigured lock table, `terraform init` fails with cryptic DynamoDB errors.

**Prevention:**
1. **Create the DynamoDB lock table in the bootstrap project alongside the S3 bucket.** The lock table must exist before other Terraform projects can use it (same chicken-and-egg as the bucket). The bootstrap project creates: S3 bucket + DynamoDB lock table.
2. **Use a clear naming convention.** Lock table: `ferry-terraform-locks` (or `terraform-state-lock`). Application table: `ferry-webhook-dedup`. Names should make the purpose obvious.
3. **The lock table schema is fixed:** Partition key must be `LockID` (String). No sort key. This is a Terraform requirement, not a choice.
4. **All non-bootstrap Terraform projects reference the same lock table** via their `backend "s3" { dynamodb_table = "ferry-terraform-locks" }` block.

**Detection:**
- `terraform init` errors mentioning "DynamoDB" or "LockID"
- Two `terraform apply` processes running simultaneously without lock contention errors (lock table is missing)
- Application code writing to the Terraform lock table or vice versa

**Phase relevance:** Bootstrap step, same as Pitfall 1.

**Confidence:** HIGH -- DynamoDB locking with S3 backend is thoroughly documented by HashiCorp.

---

### Pitfall 3: OIDC Provider Thumbprint -- AWS No Longer Validates But Terraform Still Requires It

**What goes wrong:** When creating an `aws_iam_openid_connect_provider` for GitHub Actions OIDC, Terraform requires the `thumbprint_list` argument. Historically, this had to be the SHA-1 thumbprint of the GitHub OIDC provider's TLS certificate. AWS changed this in mid-2023 -- IAM OIDC providers now use a library of trusted CAs and do NOT validate the thumbprint for providers using trusted CAs (like GitHub). However, Terraform still requires the field syntactically. Teams waste hours computing the "correct" thumbprint, or worse, hardcode an old thumbprint that no longer matches GitHub's certificate (GitHub rotates certificates).

**Why it happens:** The `thumbprint_list` is a required field in the `aws_iam_openid_connect_provider` Terraform resource. AWS's change to ignore thumbprints for trusted-CA providers was a server-side change -- the API still accepts the field, it just does not validate it for certain providers. Terraform's AWS provider has not made the field optional because the AWS API still requires it in the request.

**Consequences:** If you hardcode a specific thumbprint, it works today but breaks if GitHub rotates their certificate AND AWS reverts the trusted-CA behavior. If you compute it dynamically using a TLS connection, it adds fragility. If you use a stale value from a blog post, it may or may not work (it will today because AWS ignores it, but this is not guaranteed).

**Prevention:**
1. **Use a dummy/placeholder thumbprint.** Since AWS does not validate it for GitHub's OIDC provider, you can use any valid-format thumbprint. The common convention is to use `"6938fd4d98bab03faadb97b34396831e3780aea1"` (GitHub's historical thumbprint) or a string of 40 zeros. Include a comment explaining why.
2. **Use the `aws_iam_openid_connect_provider` data source if the provider already exists.** Avoid creating duplicate OIDC providers (only one per issuer URL per account).
3. **Add a lifecycle comment in the Terraform code:**
   ```hcl
   # AWS ignores thumbprints for OIDC providers that use trusted CAs (like GitHub).
   # This value is required by the API but not validated. See:
   # https://github.blog/changelog/2023-06-27-github-actions-update-on-oidc-based-deployments-to-aws/
   thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
   ```

**Detection:**
- Hours spent debugging "invalid thumbprint" errors (that may not actually be thumbprint-related)
- `terraform plan` showing thumbprint changes on every run (dynamic computation returning different values)
- OIDC authentication failures blamed on thumbprint when the real issue is the trust policy

**Phase relevance:** OIDC setup (shared IAM resources in `iac/teams/platform/aws/staging/shared/`).

**Confidence:** HIGH -- AWS's June 2023 change to ignore thumbprints for trusted CAs is well-documented. Terraform's requirement for the field is current behavior.

---

### Pitfall 4: OIDC Trust Policy Subject Claim Mismatch -- Deployment Silently Denied

**What goes wrong:** The IAM role's trust policy for OIDC includes a `Condition` block that restricts which GitHub repos/branches/environments can assume the role. The `sub` claim format from GitHub Actions is `repo:{owner}/{repo}:ref:refs/heads/{branch}` for branch-triggered workflows and `repo:{owner}/{repo}:environment:{env_name}` for environment-scoped workflows. Getting this string wrong -- even slightly (wrong case, wrong format, using `*` incorrectly) -- means `AssumeRoleWithWebIdentity` silently fails with "Not authorized to perform sts:AssumeRoleWithWebIdentity."

**Why it happens:** The trust policy condition uses `StringEquals` or `StringLike` on the `token.actions.githubusercontent.com:sub` claim. Common mistakes:
- Using `StringEquals` when you need wildcard matching (`StringLike` with `*`)
- Forgetting that `workflow_dispatch` events have `ref:refs/heads/{branch}` in the sub claim, NOT the triggering ref
- Getting the repo owner case wrong (GitHub is case-insensitive, IAM is not)
- Using `repo:owner/repo:*` thinking it matches all refs, but `StringLike` requires `repo:owner/repo:ref:refs/heads/*` or `repo:owner/repo:*`
- Confusing `aud` (audience) claim -- GitHub uses `sts.amazonaws.com` by default

**Consequences:** The self-deploy workflow fails with an opaque STS error. OIDC debugging is painful because the error messages do not tell you WHICH condition failed. You see "Access Denied" with no further detail.

**Prevention:**
1. **Start with a permissive condition, then tighten.** For initial setup, use `StringLike` with `repo:{owner}/{repo}:*`. Once working, restrict to specific branches:
   ```json
   {
     "Condition": {
       "StringLike": {
         "token.actions.githubusercontent.com:sub": "repo:your-org/ferry:ref:refs/heads/main"
       },
       "StringEquals": {
         "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
       }
     }
   }
   ```
2. **Test with `aws sts get-caller-identity` as the first step in your workflow.** If OIDC works, this returns the assumed role ARN. If it fails, you know immediately (before any deployment steps waste time).
3. **Log the OIDC token claims for debugging.** In the GHA workflow, you can decode the OIDC token (it's a JWT) to see the actual `sub` claim being sent. Compare it against your trust policy.
4. **Use lowercase for the repo owner in the trust policy.** GitHub normalizes org/user names to lowercase in OIDC tokens, even if the GitHub UI shows mixed case.
5. **For self-deploy, the subject claim uses `ref:refs/heads/main` (the workflow_dispatch default ref).** This is because workflow_dispatch runs on the default branch. If you dispatch to a non-default branch ref, the sub claim reflects that ref.

**Detection:**
- `AssumeRoleWithWebIdentity` failing with "Not authorized" in GHA logs
- OIDC working for one workflow but not another (different trigger types produce different sub claims)
- Works in one repo but not another (repo name case mismatch)

**Phase relevance:** OIDC IAM role creation and self-deploy workflow. This is the most common failure point when setting up GHA-to-AWS auth.

**Confidence:** HIGH -- OIDC claim formats are documented by GitHub and the trust policy syntax is standard IAM.

---

### Pitfall 5: Lambda Function URL Auth Type NONE Exposes Unauthenticated Endpoint

**What goes wrong:** Lambda Function URLs with `AuthType: NONE` are publicly accessible to anyone on the internet. There is no AWS-level authentication -- anyone who knows the URL can invoke the Lambda. For a webhook receiver this is intentional (GitHub must be able to POST to it without AWS credentials), but it means the Lambda is exposed to arbitrary traffic: bots, scanners, DDoS attempts, and forged webhook payloads.

**Why it happens:** `AuthType: NONE` means AWS does not require SigV4 signing on the request. The only protection is application-level: the HMAC-SHA256 webhook signature validation that Ferry implements. If signature validation has a bug, is bypassed, or throws an unhandled exception before validation completes, the Lambda processes untrusted input.

**Consequences:**
- **Cost exposure:** Without any protection, a bot hitting the Function URL can invoke the Lambda millions of times. Lambda charges per invocation and per GB-second. A sustained attack could generate significant AWS bills.
- **Security:** If signature validation is bypassed, an attacker could trigger fake deployments or read ferry.yaml from arbitrary repos.
- **Noise:** CloudWatch logs fill with invalid requests, making real issues harder to find.

**Prevention:**
1. **Signature validation must be the absolute first thing the handler does.** Before JSON parsing, before DynamoDB writes, before any processing. Return 401 immediately if invalid.
2. **Add a resource policy to the Function URL** to restrict source IPs to GitHub's webhook IP ranges. GitHub publishes their IP ranges at `https://api.github.com/meta` (the `hooks` array). However, these IPs change periodically, so this is defense-in-depth, not the primary control.
3. **Set reserved concurrency on the Lambda** to limit blast radius. If you set reserved concurrency to 10, at most 10 concurrent invocations can run -- limiting both cost and impact of a flood. Ferry's legitimate traffic (a few webhooks per minute at most) needs only 1-2 concurrent invocations.
4. **Enable Lambda function URL throttling** (if available in your region/config) or put CloudFront + WAF in front for rate limiting (adds complexity, maybe overkill for v1).
5. **Monitor invocation count.** Set a CloudWatch alarm on the Lambda's `Invocations` metric. If it exceeds N per minute (e.g., 100), alert. Legitimate webhook traffic is much lower.

**Detection:**
- Unexpectedly high Lambda invocation counts
- CloudWatch logs showing repeated signature validation failures
- AWS bill spikes from Lambda invocations

**Phase relevance:** Lambda + Function URL deployment in `iac/teams/platform/aws/staging/us_east_1/ferry_backend/`.

**Confidence:** HIGH -- Function URL auth types and their security implications are well-documented.

---

### Pitfall 6: Secrets Manager Secret Value Not Managed by Terraform -- Lifecycle Mismatch

**What goes wrong:** Terraform creates the Secrets Manager secret resource (the "container"), but the actual secret value (GitHub App private key, webhook secret, App ID) is stored separately. The common mistake is one of two extremes: (a) putting the actual secret value in Terraform code/variables (which means it ends up in state files and version control), or (b) creating an empty secret in Terraform and planning to fill it manually, but forgetting to do so before the Lambda tries to read it.

**Why it happens:** Terraform's `aws_secretsmanager_secret` creates the secret metadata. `aws_secretsmanager_secret_version` stores the actual value. If you put the private key in a Terraform variable, it's stored in plaintext in the Terraform state file (which is in S3 -- encrypted at rest, but readable by anyone with state access). If you skip `aws_secretsmanager_secret_version` entirely, the secret exists but has no value -- Lambda reads it and gets an error or empty string.

**Consequences:**
- **Scenario A (value in TF):** Private key is in Terraform state, readable by anyone with S3 access to the state bucket. This is a secret leak.
- **Scenario B (empty secret):** Lambda starts, tries to read the private key from Secrets Manager, gets an error or empty string. JWT generation fails. All webhook processing fails. No error message tells you "the secret is empty" -- you get a cryptic cryptography error about invalid PEM format.

**Prevention:**
1. **Create the secret container in Terraform. Store the value manually via AWS CLI or Console.** This is the standard pattern:
   ```hcl
   resource "aws_secretsmanager_secret" "github_app_private_key" {
     name        = "ferry/github-app-private-key"
     description = "GitHub App private key for Ferry webhook processing"
     # NOTE: Secret value is set manually. Do NOT use aws_secretsmanager_secret_version
     # with the actual key in Terraform -- it would be stored in state.
   }
   ```
   Then manually: `aws secretsmanager put-secret-value --secret-id ferry/github-app-private-key --secret-string file://private-key.pem`
2. **Document the manual step prominently.** In the Terraform code, in the README, and in any setup runbook. This is one of Ferry's explicit manual steps.
3. **Add a health check to the Lambda** that verifies secrets are readable at startup (cold start). If the secret is empty or unreadable, log a clear error: "FATAL: Secret ferry/github-app-private-key has no value. Run: aws secretsmanager put-secret-value ..."
4. **Use `ignore_changes` lifecycle if you do use `aws_secretsmanager_secret_version`.** If you bootstrap the secret with a placeholder value via Terraform and later update it manually, add `lifecycle { ignore_changes = [secret_string] }` to prevent Terraform from reverting to the placeholder on the next apply.
5. **Three separate secrets, not one JSON blob.** Store App ID, private key, and webhook secret as three separate secrets. This makes rotation and access control granular. Name them clearly: `ferry/github-app-id`, `ferry/github-app-private-key`, `ferry/github-app-webhook-secret`.

**Detection:**
- Lambda errors about "invalid PEM" or "secret not found"
- Terraform state file containing a `secret_string` attribute (search for it!)
- Secrets Manager console showing a secret with "No value" or a placeholder

**Phase relevance:** Shared resources in `iac/teams/platform/aws/staging/shared/` and the manual GitHub App registration step.

**Confidence:** HIGH -- Secrets Manager + Terraform lifecycle is a well-established pattern.

---

### Pitfall 7: Self-Deploy Circular Dependency -- Workflow Cannot Deploy What Does Not Yet Exist

**What goes wrong:** The self-deploy GitHub Actions workflow builds the Ferry Lambda container, pushes it to ECR, and updates the Lambda function. But on initial setup, none of these exist yet: no ECR repo, no Lambda function, no IAM role for OIDC. The workflow cannot deploy to resources that Terraform has not yet created. Conversely, the Lambda Terraform resource needs an initial container image to exist in ECR (you cannot create a Lambda with `PackageType: Image` without specifying an image URI). This creates a three-way circular dependency: Terraform needs an image -> image needs ECR -> ECR needs Terraform.

**Why it happens:** Lambda functions with `PackageType: Image` require a valid `image_uri` at creation time. Terraform will fail to create the Lambda if the ECR repo is empty or the image URI does not resolve to a valid manifest. The self-deploy workflow cannot run until the Lambda exists (nothing to deploy to). And the ECR repo cannot have an image until someone pushes one.

**Consequences:** First-time setup is blocked. `terraform apply` fails because the image does not exist. The workflow cannot run because the Lambda does not exist. You are stuck.

**Prevention:**
1. **Bootstrap with a placeholder image.** Create the ECR repo first (in the bootstrap/global Terraform project). Push a minimal "hello world" Lambda container image manually or via a one-time script:
   ```bash
   # One-time bootstrap: push a placeholder image
   docker pull public.ecr.aws/lambda/python:3.14
   docker tag public.ecr.aws/lambda/python:3.14 \
     ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ferry/backend:bootstrap
   aws ecr get-login-password | docker login --username AWS --password-stdin \
     ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
   docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ferry/backend:bootstrap
   ```
   Then Terraform references `ferry/backend:bootstrap` as the initial image. The self-deploy workflow later replaces it with the real image.
2. **Split Terraform into stages that respect the dependency order:**
   - Stage 1 (bootstrap): S3 bucket, DynamoDB lock table
   - Stage 2 (global): ECR repo (+ push placeholder image manually)
   - Stage 3 (shared): IAM roles, OIDC provider, Secrets Manager
   - Stage 4 (ferry_backend): Lambda + Function URL + DynamoDB app table (references ECR image)
3. **Use `image_uri` as a Terraform variable with a default.** The variable defaults to the bootstrap image tag. The self-deploy workflow overrides it with the real image. Terraform does not need to change after initial setup because Lambda code updates happen via the AWS API (not Terraform).
4. **Mark the Lambda's `image_uri` as ignored in lifecycle:**
   ```hcl
   resource "aws_lambda_function" "ferry" {
     function_name = "ferry-backend"
     package_type  = "Image"
     image_uri     = "${var.ecr_repo_url}:${var.image_tag}"
     # ...
     lifecycle {
       ignore_changes = [image_uri]
     }
   }
   ```
   This prevents Terraform from reverting the image to the bootstrap tag after the self-deploy workflow updates it.

**Detection:**
- `terraform apply` failing with "image manifest not found" or "invalid image URI"
- Self-deploy workflow failing with "Function not found"
- Lambda running the placeholder/bootstrap image in production (forgot to trigger the real deploy)

**Phase relevance:** This is the central coordination challenge of v1.1. Must be designed before writing any Terraform.

**Confidence:** HIGH -- the image-before-Lambda dependency is a well-known Terraform + Lambda container pattern.

---

## Moderate Pitfalls

---

### Pitfall 8: Lambda Function URL Payload Format Version Mismatch

**What goes wrong:** Lambda Function URLs support two payload format versions: 1.0 and 2.0. Version 2.0 is the default for new Function URLs and has a different event structure than what you might expect from API Gateway experience. Specifically: the `body` field is a string (not pre-parsed JSON), `headers` are lowercase, `requestContext` has a different structure, and multi-value headers are joined with commas instead of being arrays.

**Why it happens:** Developers who have worked with API Gateway Lambda proxy integration (which uses its own event format) assume Function URL events look the same. They do not. If your Lambda handler is written for one format and the Function URL is configured for another, field access fails at runtime.

**Consequences:** Lambda handler crashes on the first webhook because it cannot find expected fields in the event. The error message is a generic KeyError or AttributeError, not "wrong payload format."

**Prevention:**
1. **Explicitly set `invoke_mode = "BUFFERED"` and use payload format 2.0 in Terraform:**
   ```hcl
   resource "aws_lambda_function_url" "webhook" {
     function_name      = aws_lambda_function.ferry.function_name
     authorization_type = "NONE"
     invoke_mode        = "BUFFERED"
   }
   ```
2. **Document the exact event structure your handler expects.** Create a test fixture with a real Function URL event (payload v2.0):
   ```json
   {
     "version": "2.0",
     "requestContext": { "http": { "method": "POST", "path": "/" } },
     "headers": { "x-hub-signature-256": "sha256=...", "x-github-delivery": "..." },
     "body": "{\"action\":\"...\"}",
     "isBase64Encoded": false
   }
   ```
3. **Test with the exact payload format in unit tests.** Do not assume. Create fixtures from actual Function URL invocations.
4. **Handle `isBase64Encoded: true`.** If the request body contains binary data, the Function URL base64-encodes it. GitHub webhooks are JSON (not binary), so this should not happen, but defensive code is cheap.

**Detection:**
- Lambda handler KeyError on `event["body"]` or `event["headers"]`
- Webhook processing failing on the very first request after deployment
- Unit tests passing but real invocations failing (test fixtures use wrong event format)

**Phase relevance:** Lambda + Function URL Terraform and handler integration testing.

**Confidence:** HIGH -- Lambda Function URL event format is documented and stable.

---

### Pitfall 9: ECR Repository Lifecycle Policy Missing -- Images Accumulate Forever

**What goes wrong:** Every self-deploy workflow run pushes a new container image to ECR. Without a lifecycle policy, images accumulate indefinitely. ECR charges for storage ($0.10/GB/month). Over months, this adds up -- especially if images are large (Lambda containers with Python + dependencies can be 200-500 MB).

**Why it happens:** ECR lifecycle policies are not created by default. They must be explicitly configured. In the rush to get deployment working, this is easily forgotten.

**Consequences:** ECR storage costs grow linearly with deployments. Over time, this becomes a noticeable cost. More importantly, the ECR console becomes unusable with hundreds of image tags, making it hard to find the currently deployed version.

**Prevention:**
1. **Add a lifecycle policy to the ECR repo in Terraform:**
   ```hcl
   resource "aws_ecr_lifecycle_policy" "ferry" {
     repository = aws_ecr_repository.ferry.name
     policy = jsonencode({
       rules = [{
         rulePriority = 1
         description  = "Keep last 10 images"
         selection = {
           tagStatus   = "any"
           countType   = "imageCountMoreThan"
           countNumber = 10
         }
         action = { type = "expire" }
       }]
     })
   }
   ```
2. **Keep the last N images (e.g., 10-20), not a time-based policy.** This ensures you always have recent images for rollback, regardless of deployment frequency.
3. **Tag images meaningfully.** Use `main-{short_sha}` or `pr-{number}` tags so you can identify which image corresponds to which deploy.

**Detection:**
- ECR storage costs increasing over time
- Hundreds of image tags in the ECR console
- `terraform plan` not showing any ECR lifecycle policy resource

**Phase relevance:** ECR repo creation in `iac/global/cloud/aws/ecr/`.

**Confidence:** HIGH -- ECR lifecycle policies are standard practice.

---

### Pitfall 10: Lambda IAM Role Missing Permissions -- Fails at Runtime, Not at Deploy

**What goes wrong:** Terraform creates the Lambda function and its IAM execution role, but the role's policy is missing permissions for one or more AWS services the Lambda needs. Common missing permissions for Ferry: `secretsmanager:GetSecretValue` (reading GitHub App credentials), `dynamodb:PutItem`/`GetItem` (webhook dedup), `logs:CreateLogGroup`/`CreateLogStream`/`PutLogEvents` (CloudWatch Logs). Terraform apply succeeds (IAM creation does not validate permissions against usage), but the Lambda fails at runtime.

**Why it happens:** IAM policies are declarative -- you specify what the role CAN do, but there is no validation that it has everything it NEEDS. Terraform does not know what AWS APIs the Lambda code will call. The policy must be manually kept in sync with the code.

**Consequences:** Lambda deploys successfully but crashes on the first invocation. Error messages like "User: arn:aws:sts::...:assumed-role/ferry-lambda-role/ferry-backend is not authorized to perform: secretsmanager:GetSecretValue" in CloudWatch logs. Each missing permission requires a Terraform change, apply, and re-test cycle.

**Prevention:**
1. **Define the complete IAM policy upfront based on the Lambda's known API calls:**
   ```hcl
   # Ferry Lambda needs:
   # - DynamoDB: read/write to dedup table
   # - Secrets Manager: read GitHub App credentials
   # - CloudWatch Logs: write logs (standard for any Lambda)
   data "aws_iam_policy_document" "ferry_lambda" {
     statement {
       sid    = "DynamoDB"
       effect = "Allow"
       actions = [
         "dynamodb:PutItem",
         "dynamodb:GetItem",
         "dynamodb:Query",
       ]
       resources = [aws_dynamodb_table.webhook_dedup.arn]
     }
     statement {
       sid    = "SecretsManager"
       effect = "Allow"
       actions = ["secretsmanager:GetSecretValue"]
       resources = [
         aws_secretsmanager_secret.github_app_private_key.arn,
         aws_secretsmanager_secret.github_app_id.arn,
         aws_secretsmanager_secret.github_app_webhook_secret.arn,
       ]
     }
     statement {
       sid    = "CloudWatchLogs"
       effect = "Allow"
       actions = [
         "logs:CreateLogGroup",
         "logs:CreateLogStream",
         "logs:PutLogEvents",
       ]
       resources = ["arn:aws:logs:*:*:*"]
     }
   }
   ```
2. **Use specific resource ARNs, not `"*"`.** Least-privilege from the start. Wildcards are harder to tighten later.
3. **Test with `moto` in unit tests, but also do a smoke test against real AWS.** Moto does not validate IAM permissions -- it happily allows any operation. The only way to validate permissions is to actually invoke the Lambda in the real account.
4. **Add a Lambda smoke test to the self-deploy workflow.** After updating the Lambda, invoke it with a test event and verify it returns 200. If it returns an error, the deployment is not complete.

**Detection:**
- Lambda CloudWatch logs showing "AccessDeniedException" or "is not authorized"
- Lambda invocations returning 500 with permission error in the response
- Moto tests passing but real Lambda failing (moto does not enforce IAM)

**Phase relevance:** IAM in `iac/teams/platform/aws/staging/shared/` and Lambda in `us_east_1/ferry_backend/`.

**Confidence:** HIGH -- IAM permission gaps are the most common Lambda deployment issue.

---

### Pitfall 11: GitHub App Registration Timing -- Webhook URL Needs to Exist First

**What goes wrong:** When registering a GitHub App (manual step), you must provide a webhook URL. But the Lambda Function URL does not exist until Terraform creates it. And Terraform cannot create it until you have the App's credentials (App ID, private key) to store in Secrets Manager. This is another circular dependency: App registration needs URL -> URL needs Lambda -> Lambda needs App credentials -> credentials come from App registration.

**Why it happens:** GitHub App registration is a one-time manual process that produces outputs (App ID, private key, webhook secret) which are inputs to the infrastructure. The webhook URL is an output of the infrastructure that is an input to the App registration.

**Consequences:** You either register the App with a placeholder URL (and must update it later), or you deploy infrastructure with placeholder secrets (and the Lambda fails until real secrets are provided).

**Prevention:**
1. **Accept the two-pass setup. The order is:**
   - Pass 1: Deploy all Terraform (Lambda + Function URL + Secrets Manager). Note the Function URL.
   - Pass 2: Register the GitHub App using the Function URL as the webhook URL. Get App ID, private key, webhook secret.
   - Pass 3: Store the credentials in Secrets Manager (manual `aws secretsmanager put-secret-value`).
   - The Lambda is now functional.
2. **Alternatively, register the App first with a placeholder URL (`https://example.com`).** Deploy infrastructure. Update the App's webhook URL to the real Function URL via GitHub API or Settings page. This works and is simpler, but requires remembering to update the URL.
3. **Document this sequence as a runbook.** It is not automatable (GitHub App registration requires clicking through a web UI). Flag it as a manual step prominently.
4. **Use Terraform output to print the Function URL:**
   ```hcl
   output "webhook_url" {
     value       = aws_lambda_function_url.webhook.function_url
     description = "Use this URL as the Webhook URL when registering the GitHub App"
   }
   ```

**Detection:**
- GitHub App webhook deliveries failing (URL points to placeholder or does not exist)
- Lambda never receiving webhooks (App configured with wrong URL)
- Secrets Manager secrets empty (Pass 3 was forgotten)

**Phase relevance:** The coordination between Terraform deployment and GitHub App registration. Must be planned as a documented sequence.

**Confidence:** HIGH -- GitHub App registration is manual and this ordering constraint is inherent.

---

### Pitfall 12: Terraform Remote State References Between Projects -- Coupling and Ordering

**What goes wrong:** The ConvergeBio/iac-tf pattern uses `terraform_remote_state` data sources to share outputs between Terraform projects (e.g., the ECR repo URL from the global project is referenced by the staging project). If the referenced project's state does not exist yet (has not been applied), the `terraform_remote_state` data source fails with a cryptic error. Also, if someone renames an output in the upstream project, downstream projects break on next plan/apply.

**Why it happens:** `terraform_remote_state` reads from the S3 state file directly. It requires: (a) the state file to exist at the expected S3 key, (b) the output to exist with the expected name and type. There is no schema validation or dependency tracking between projects -- it is a loose coupling that breaks silently.

**Consequences:** `terraform plan` or `terraform apply` in a downstream project fails because an upstream project has not been applied yet, or an output was renamed/removed. Error messages reference the S3 key and output name but do not suggest "you need to apply project X first."

**Prevention:**
1. **Document the apply order explicitly:**
   ```
   Apply order:
   1. iac/global/cloud/aws/backend/     (S3 bucket + DDB lock table)
   2. iac/global/cloud/aws/ecr/         (ECR repo)
   3. iac/teams/platform/aws/staging/shared/   (IAM, OIDC, Secrets Manager)
   4. iac/teams/platform/aws/staging/us_east_1/ferry_backend/  (Lambda, Function URL, DDB app table)
   ```
2. **Use consistent output names and treat them as a contract.** Do not rename outputs without updating all downstream consumers.
3. **Consider using SSM Parameter Store for cross-project references** instead of `terraform_remote_state`. Write outputs as SSM parameters, read them with `aws_ssm_parameter` data sources. This is more resilient (parameters persist even if state is refactored) and more discoverable.
4. **Keep the number of cross-project references minimal.** The fewer dependencies, the less fragile the setup. For Ferry's staging, the chain is short: ECR URL from global -> Lambda project. IAM role ARN from shared -> Lambda project.

**Detection:**
- `terraform plan` failing with "Unable to find remote state" or "output not found"
- Applying projects out of order during initial setup
- Downstream projects breaking after upstream output changes

**Phase relevance:** All Terraform projects in the `iac/` hierarchy.

**Confidence:** HIGH -- `terraform_remote_state` coupling issues are a common Terraform operational problem.

---

### Pitfall 13: Lambda Environment Variables for Secrets Manager ARNs -- Hardcoded Account IDs

**What goes wrong:** The Lambda function needs environment variables pointing to its Secrets Manager secrets, DynamoDB table name, and other configuration. A common mistake is hardcoding AWS account IDs or ARNs in Terraform variables instead of using references. This means the configuration is not portable between accounts (staging vs production) and fails if resources are recreated with different names.

**Why it happens:** Copy-pasting ARNs from the AWS console is faster than setting up proper Terraform references. Or using `var.account_id` instead of `data.aws_caller_identity.current.account_id`. The configuration works in one account but breaks when you create a second environment.

**Consequences:** Deploying to a second environment (production) requires manually finding and replacing all hardcoded values. Missing one means the Lambda in production points to staging's secrets or table.

**Prevention:**
1. **Use Terraform resource references for all ARNs and names:**
   ```hcl
   resource "aws_lambda_function" "ferry" {
     # ...
     environment {
       variables = {
         TABLE_NAME                  = aws_dynamodb_table.webhook_dedup.name
         SECRET_GITHUB_APP_KEY_ARN   = aws_secretsmanager_secret.github_app_private_key.arn
         SECRET_GITHUB_APP_ID_ARN    = aws_secretsmanager_secret.github_app_id.arn
         SECRET_WEBHOOK_SECRET_ARN   = aws_secretsmanager_secret.github_app_webhook_secret.arn
       }
     }
   }
   ```
2. **Use `data.aws_caller_identity.current.account_id`** for any account-specific values.
3. **Use `data.aws_region.current.name`** instead of hardcoding region strings.
4. **Pass secret ARNs, not secret names.** ARNs are globally unique. Names can conflict across accounts/regions.

**Detection:**
- Terraform variables with hardcoded 12-digit account IDs
- Lambda environment variables that do not reference Terraform resources
- Environment parity issues (works in staging, not in production)

**Phase relevance:** Lambda configuration in `us_east_1/ferry_backend/`.

**Confidence:** HIGH -- standard Terraform best practice.

---

## Minor Pitfalls

---

### Pitfall 14: S3 Backend Key Path Conflicts Between Terraform Projects

**What goes wrong:** Each Terraform project in the `iac/` hierarchy needs a unique `key` in the S3 backend block. If two projects accidentally use the same key, they overwrite each other's state files. This corrupts both projects' state.

**Prevention:**
1. **Use a key that mirrors the directory path:**
   ```hcl
   backend "s3" {
     bucket = "ferry-terraform-state"
     key    = "global/cloud/aws/ecr/terraform.tfstate"
     region = "us-east-1"
   }
   ```
2. **Include the key in a code review checklist** for any new Terraform project.
3. **List all state keys periodically** (`aws s3 ls s3://ferry-terraform-state/ --recursive`) to verify uniqueness.

**Phase relevance:** Every Terraform project setup.

**Confidence:** HIGH.

---

### Pitfall 15: DynamoDB On-Demand vs Provisioned -- Terraform Default Is Provisioned

**What goes wrong:** Terraform's `aws_dynamodb_table` resource defaults to `billing_mode = "PROVISIONED"` with `read_capacity = 0` and `write_capacity = 0` if not specified. This creates a table that cannot serve any requests. The error at runtime is "ProvisionedThroughputExceededException" which is confusing when you thought you were using on-demand.

**Prevention:**
1. **Always explicitly set `billing_mode = "PAY_PER_REQUEST"`** for on-demand:
   ```hcl
   resource "aws_dynamodb_table" "webhook_dedup" {
     name         = "ferry-webhook-dedup"
     billing_mode = "PAY_PER_REQUEST"
     hash_key     = "pk"
     range_key    = "sk"
     # ...
   }
   ```
2. **Do not rely on defaults for DynamoDB billing.** The Terraform default and the AWS console default differ (console defaults to on-demand for new tables).

**Phase relevance:** DynamoDB table creation in `us_east_1/ferry_backend/`.

**Confidence:** HIGH.

---

### Pitfall 16: Lambda Timeout Too Low for Cold Start + Processing

**What goes wrong:** Terraform's default Lambda timeout is 3 seconds. Ferry's Lambda needs to: cold start Python + dependencies (~1-3s for container images), validate webhook signature, write to DynamoDB, generate JWT, call GitHub API (installation token + ferry.yaml + compare + dispatch), and post check runs. 3 seconds is not enough. The Lambda times out, returns no response, GitHub retries the webhook, and the retry also times out -- creating a loop.

**Prevention:**
1. **Set timeout to 30 seconds in Terraform:**
   ```hcl
   resource "aws_lambda_function" "ferry" {
     timeout = 30  # seconds
     # ...
   }
   ```
2. **Set memory to at least 256 MB.** Lambda allocates CPU proportionally to memory. 128 MB (default) gives minimal CPU, making cold starts slower. 256 MB is a good balance.
3. **Monitor actual execution duration in CloudWatch.** If P99 duration exceeds 8 seconds, investigate -- GitHub has a 10-second expectation for webhook responses.

**Phase relevance:** Lambda configuration in `us_east_1/ferry_backend/`.

**Confidence:** HIGH.

---

### Pitfall 17: Function URL Output Not Predictable -- Cannot Pre-Configure GitHub App

**What goes wrong:** Lambda Function URL domains are auto-generated by AWS (format: `https://<url-id>.lambda-url.<region>.on.aws/`). The `url-id` is random and not predictable before creation. You cannot know the URL until after `terraform apply`. This makes it impossible to register the GitHub App with the correct URL before deploying the infrastructure.

**Prevention:**
1. **Accept this as a sequential dependency** (see Pitfall 11). Deploy infra first, register App second.
2. **Add a custom domain via CloudFront if you want a stable URL.** This adds complexity but gives you a domain like `webhook.ferry.dev` that survives Lambda recreation. For v1 staging, the auto-generated URL is fine.
3. **Output the URL prominently in Terraform:**
   ```hcl
   output "webhook_url" {
     value       = aws_lambda_function_url.webhook.function_url
     description = "GitHub App Webhook URL"
   }
   ```

**Phase relevance:** Coordination between Terraform and GitHub App registration.

**Confidence:** HIGH.

---

### Pitfall 18: Self-Deploy Workflow Permissions -- Missing `id-token: write`

**What goes wrong:** The self-deploy GHA workflow needs `permissions: id-token: write` to request an OIDC token for AWS authentication. If this permission is missing, the `aws-actions/configure-aws-credentials` step fails with "Error: Credentials could not be loaded" or "Unable to get OIDC token." The error message does not say "missing id-token permission."

**Prevention:**
1. **Always include OIDC permissions in the workflow:**
   ```yaml
   permissions:
     id-token: write    # Required for OIDC
     contents: read     # Required for checkout
   ```
2. **Note:** Setting explicit `permissions` in a workflow disables ALL default permissions. You must explicitly list everything you need. Missing `contents: read` means `actions/checkout` fails.
3. **Test the OIDC exchange as the first step** (`aws sts get-caller-identity`) before doing any real work.

**Phase relevance:** Self-deploy workflow creation.

**Confidence:** HIGH.

---

### Pitfall 19: ECR Login Region Mismatch

**What goes wrong:** The ECR repo is in one region (e.g., `us-east-1`), but the `aws ecr get-login-password` command or `aws-actions/amazon-ecr-login` action is configured for a different region. Docker push fails with "no basic auth credentials" or "repository does not exist."

**Prevention:**
1. **Ensure the region passed to ECR login matches the ECR repo's region.**
2. **Use the same region variable/input throughout the workflow.** Do not hardcode regions in some places and use variables in others.

**Phase relevance:** Self-deploy workflow.

**Confidence:** HIGH.

---

## Phase-Specific Warnings

| Phase/Step | Likely Pitfall | Mitigation | Severity |
|------------|---------------|------------|----------|
| Bootstrap: S3 + DDB lock | Chicken-and-egg (Pitfall 1) | Two-step: local state then migrate | CRITICAL |
| Bootstrap: S3 + DDB lock | Lock table schema (Pitfall 2) | Use `LockID` as partition key | HIGH |
| Bootstrap: S3 + DDB lock | State key conflicts (Pitfall 14) | Mirror directory path in key | MODERATE |
| Global: ECR repo | No lifecycle policy (Pitfall 9) | Add lifecycle policy in TF | MODERATE |
| Global: ECR repo | Self-deploy needs image first (Pitfall 7) | Push placeholder image | CRITICAL |
| Shared: OIDC provider | Thumbprint confusion (Pitfall 3) | Use historical thumbprint, comment it | HIGH |
| Shared: OIDC IAM role | Sub claim mismatch (Pitfall 4) | Start permissive, tighten later | CRITICAL |
| Shared: Secrets Manager | Value lifecycle mismatch (Pitfall 6) | TF creates container, manual value | HIGH |
| Shared: IAM Lambda role | Missing permissions (Pitfall 10) | Define complete policy upfront | HIGH |
| Backend: Lambda | Timeout too low (Pitfall 16) | Set 30s timeout, 256MB memory | HIGH |
| Backend: Lambda | Hardcoded ARNs (Pitfall 13) | Use TF resource references | MODERATE |
| Backend: Lambda | Image circular dependency (Pitfall 7) | Bootstrap image + ignore lifecycle | CRITICAL |
| Backend: Function URL | Auth NONE exposure (Pitfall 5) | Reserved concurrency, monitoring | HIGH |
| Backend: Function URL | Payload format (Pitfall 8) | Explicitly test v2.0 format | MODERATE |
| Backend: Function URL | URL not predictable (Pitfall 17) | Accept sequential dependency | LOW |
| Backend: DynamoDB | Billing mode default (Pitfall 15) | Explicit PAY_PER_REQUEST | HIGH |
| Self-deploy: GHA workflow | Missing id-token permission (Pitfall 18) | Explicit permissions block | HIGH |
| Self-deploy: GHA workflow | ECR region mismatch (Pitfall 19) | Consistent region variable | MODERATE |
| Self-deploy: GHA workflow | OIDC sub claim (Pitfall 4) | Match trust policy to trigger type | CRITICAL |
| Cross-project: remote state | Apply ordering (Pitfall 12) | Document and enforce order | HIGH |
| Manual: GitHub App registration | Timing/ordering (Pitfall 11) | Deploy infra first, register second | HIGH |

---

## Recommended Setup Sequence

Based on the pitfalls above, the safe order of operations is:

```
1. terraform apply  iac/global/cloud/aws/backend/
   (bootstrap: S3 bucket + DDB lock table, start with local state, migrate to S3)

2. terraform apply  iac/global/cloud/aws/ecr/
   (creates ECR repo)

3. MANUAL: Push placeholder Docker image to ECR
   (unblocks Lambda creation)

4. terraform apply  iac/teams/platform/aws/staging/shared/
   (OIDC provider, IAM roles, Secrets Manager secret containers)

5. terraform apply  iac/teams/platform/aws/staging/us_east_1/ferry_backend/
   (Lambda + Function URL + DynamoDB app table)
   NOTE: Lambda starts with placeholder image, secrets are empty

6. MANUAL: Register GitHub App
   - Use Function URL from step 5 as webhook URL
   - Note: App ID, private key, webhook secret

7. MANUAL: Store secrets in Secrets Manager
   aws secretsmanager put-secret-value --secret-id ferry/github-app-private-key --secret-string file://private-key.pem
   aws secretsmanager put-secret-value --secret-id ferry/github-app-id --secret-string "APP_ID"
   aws secretsmanager put-secret-value --secret-id ferry/github-app-webhook-secret --secret-string "WEBHOOK_SECRET"

8. RUN: Self-deploy GHA workflow
   (builds real Ferry image, pushes to ECR, updates Lambda)

9. VERIFY: Send test webhook or install App on a test repo
```

Steps 1-5 are Terraform (automatable after bootstrap).
Steps 6-7 are manual (one-time).
Step 8 is the self-deploy workflow (automated going forward).

---

## Sources

- HashiCorp Terraform Docs: S3 Backend configuration, `terraform_remote_state` data source (training data, HIGH confidence -- stable, well-documented)
- AWS Docs: Lambda Function URLs, IAM OIDC Identity Providers, Secrets Manager, DynamoDB, ECR Lifecycle Policies (training data, HIGH confidence -- stable AWS services)
- GitHub Docs: Configuring OpenID Connect in Amazon Web Services, GitHub App registration (training data, HIGH confidence -- well-documented)
- GitHub Blog: "Update on OIDC-based deployments to AWS" (June 2023) -- thumbprint change announcement
- ConvergeBio/iac-tf patterns (from terraform-conventions.md in project memory)
- AWS Actions: `aws-actions/configure-aws-credentials` documentation for OIDC setup

**Note:** WebSearch, WebFetch, and Bash tools were unavailable during this research session. All findings are based on training data knowledge of Terraform, AWS, and GitHub. These are mature, stable technologies with well-established patterns. Confidence levels are MEDIUM-HIGH overall. Key claims to verify with live docs before implementation:
- Current Lambda Function URL payload format version defaults
- Current `aws_iam_openid_connect_provider` Terraform resource behavior for `thumbprint_list`
- Whether AWS has added built-in rate limiting for Lambda Function URLs since early 2025
- Current ECR lifecycle policy Terraform syntax (may have minor updates)
