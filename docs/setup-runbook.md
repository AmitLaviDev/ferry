# Ferry Phase 14: Setup Runbook

Complete setup instructions for registering the GitHub App, populating secrets, and verifying the self-deploy pipeline. Follow these steps after Terraform infrastructure (Phases 11-13) has been applied.

---

## Prerequisites

Before starting, confirm:

1. **AWS credentials configured** -- verify with:
   ```bash
   aws sts get-caller-identity
   ```

2. **Phases 11-13 Terraform applied** -- the Lambda Function URL, IAM roles, Secrets Manager containers, and ECR repo must already exist.

3. **Function URL** -- retrieve from Terraform output:
   ```bash
   terraform -chdir=iac/aws/staging/us-east-1/ferry_backend output -raw lambda_function_url
   ```

4. **GHA self-deploy role ARN** -- retrieve from Terraform output:
   ```bash
   terraform -chdir=iac/aws/staging/shared output -raw gha_self_deploy_role_arn
   ```

Save both values -- you will need them in the steps below.

---

## Step 1: Register GitHub App

1. Go to **Settings > Developer settings > GitHub Apps > New GitHub App**
   - Direct link: https://github.com/settings/apps/new

2. Fill in the basic information:
   - **GitHub App name:** `Ferry` (or `Ferry-Staging` for a staging-specific app)
   - **Homepage URL:** `https://github.com/<owner>/ferry` (your repo URL)

3. Configure the webhook:
   - **Webhook URL:** Paste the Function URL from the prerequisites
   - **Webhook secret:** Generate one and save it for Step 2:
     ```bash
     openssl rand -hex 20
     ```

4. Set **Repository permissions:**

   | Permission    | Access       |
   |---------------|--------------|
   | Contents      | Read         |
   | Pull requests | Read & Write |
   | Checks        | Read & Write |
   | Actions       | Write        |
   | Metadata      | Read (auto)  |

5. Subscribe to **events:**
   - [x] Push

6. **Where can this GitHub App be installed?** Select "Only on this account" (can be changed later).

7. Click **Create GitHub App**.

8. On the app settings page, note the **App ID** (displayed near the top).

9. Scroll to **Private keys** and click **Generate a private key**. Save the downloaded `.pem` file securely.

10. **Install the App** on the ferry repo:
    - Go to the app's settings page > **Install App** (left sidebar)
    - Select the account, then choose "Only select repositories" and pick the `ferry` repo
    - Click **Install**

11. Note the **Installation ID** from the URL after installation:
    ```
    https://github.com/settings/installations/{INSTALLATION_ID}
    ```

---

## Step 2: Populate Secrets Manager

Run these three commands, substituting the values from Step 1:

```bash
# App ID (from the app settings page)
aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/app-id \
  --secret-string "<APP_ID>"

# Private key (path to the downloaded .pem file)
aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/private-key \
  --secret-string "$(cat /path/to/ferry.private-key.pem)"

# Webhook secret (the hex string generated in Step 1)
aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/webhook-secret \
  --secret-string "<WEBHOOK_SECRET>"
```

Verify each secret was populated:

```bash
aws secretsmanager get-secret-value --secret-id ferry/github-app/app-id --query SecretString --output text
aws secretsmanager get-secret-value --secret-id ferry/github-app/private-key --query 'SecretString' --output text | head -c 50
aws secretsmanager get-secret-value --secret-id ferry/github-app/webhook-secret --query SecretString --output text
```

---

## Step 3: Configure GitHub Repo Secrets

Set the `AWS_DEPLOY_ROLE_ARN` repository secret so the self-deploy workflow can authenticate via OIDC:

1. Go to the ferry repo on GitHub > **Settings** > **Secrets and variables** > **Actions**
2. Click **New repository secret**
3. **Name:** `AWS_DEPLOY_ROLE_ARN`
4. **Value:** The ARN of the `ferry-gha-self-deploy` role from the prerequisites:
   ```bash
   terraform -chdir=iac/aws/staging/shared output -raw gha_self_deploy_role_arn
   ```
5. Click **Add secret**

---

## Step 4: Update Installation ID

The Lambda needs the real Installation ID to authenticate as the GitHub App. The Terraform default is a placeholder (`0`).

**Option A -- Quick (AWS CLI):**

```bash
# First, get the current environment variables
CURRENT_ENV=$(aws lambda get-function-configuration \
  --function-name ferry-backend \
  --query 'Environment.Variables' \
  --output json \
  --no-cli-pager)

# Update with the real installation ID
aws lambda update-function-configuration \
  --function-name ferry-backend \
  --environment "{\"Variables\": $(echo "$CURRENT_ENV" | jq '. + {"FERRY_INSTALLATION_ID": "<INSTALLATION_ID>"}')}" \
  --no-cli-pager
```

**Option B -- Permanent (Terraform):**

Update the `installation_id` variable in `iac/aws/staging/us-east-1/ferry_backend/terraform.tfvars`:

```hcl
installation_id = "<INSTALLATION_ID>"
```

Then apply:

```bash
terraform -chdir=iac/aws/staging/us-east-1/ferry_backend apply -input=false
```

Option B is recommended so the value persists across Terraform applies.

---

## Step 5: Trigger First Deploy

Push a commit to `main` (or merge a PR). The self-deploy workflow will:

1. Run the pytest test suite
2. Build the Docker image and push to ECR (tagged with the commit SHA)
3. Update the Lambda function code to the new image

Monitor the workflow run at:
```
https://github.com/<owner>/ferry/actions/workflows/self-deploy.yml
```

Wait for the workflow to complete successfully (green checkmark) before proceeding to verification.

---

## Step 6: Verify End-to-End

### 6a. Curl the Function URL

```bash
curl -s "$(terraform -chdir=iac/aws/staging/us-east-1/ferry_backend output -raw lambda_function_url)" | jq .
```

**Expected:** A JSON response. Even an error response is fine -- it proves the Lambda is running the real Ferry backend code (not the placeholder image).

### 6b. Test Webhook Delivery

1. Go to the GitHub App settings page > **Advanced** tab > **Recent Deliveries**
2. Find a recent delivery and click **Redeliver**
3. Check the response

**Expected:** A `200` response or a `401`/signature error. A signature mismatch on redeliver is expected because GitHub regenerates the payload but the original signature no longer matches. Any HTTP response from your Function URL proves the Lambda is receiving and processing webhooks.

### 6c. Check CloudWatch Logs

```bash
aws logs tail /aws/lambda/ferry-backend --since 5m --follow
```

**Expected:** Structured JSON log entries showing webhook processing. Look for entries indicating the Lambda received the request and attempted to validate the signature.

Press `Ctrl+C` to stop following logs.

---

## Troubleshooting

### Workflow fails at "Configure AWS credentials"
- Verify `AWS_DEPLOY_ROLE_ARN` repo secret is set correctly
- Verify the OIDC trust policy on the `ferry-gha-self-deploy` role matches the repo name (case-sensitive)

### Lambda returns 500 or crashes
- Check CloudWatch logs: `aws logs tail /aws/lambda/ferry-backend --since 10m`
- Verify all three secrets are populated (Step 2 verification commands)
- Verify the Installation ID is set (Step 4)

### Webhook returns 401 consistently (not just on redeliver)
- Verify the webhook secret in Secrets Manager matches the one configured in the GitHub App settings
- Re-populate if needed: repeat Step 2 for the webhook secret

### ECR login fails in workflow
- Verify the `ferry-gha-self-deploy` role has `ecr:GetAuthorizationToken` permission
- Check that the ECR repo `lambda-ferry-backend` exists: `aws ecr describe-repositories --repository-names lambda-ferry-backend`
