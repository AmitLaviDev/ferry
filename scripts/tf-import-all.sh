#!/usr/bin/env bash
# tf-import-all.sh -- Import existing AWS resources into Terraform state
#
# These resources were created manually or via a previous TF workspace whose
# state was lost. This script imports them into the new directory layout.
#
# Order: backend -> ecr -> oidc -> shared (matches dependency chain)
#
# Usage: ./scripts/tf-import-all.sh
#   Run from the repo root. Requires: terraform, AWS credentials.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IAC="$REPO_ROOT/iac"
ACCOUNT_ID="050068574410"
REGION="us-east-1"

echo "Ferry Terraform Import — All Projects"
echo "======================================="
echo ""
echo "Account: $ACCOUNT_ID"
echo "Region:  $REGION"
echo ""

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

import_resource() {
    local project="$1"
    local address="$2"
    local id="$3"

    echo "  terraform import $address"
    terraform -chdir="$project" import -input=false "$address" "$id" 2>&1 | tail -1
}

# ---------------------------------------------------------------------------
# 1/4: Backend (S3 state bucket)
# ---------------------------------------------------------------------------

echo "[1/4] Importing backend (S3 state bucket)..."
PROJECT="$IAC/global/cloud/aws/backend"
terraform -chdir="$PROJECT" init -input=false -reconfigure > /dev/null 2>&1

import_resource "$PROJECT" "module.s3_bucket.aws_s3_bucket.this[0]" "ferry-global-terraform-state"
import_resource "$PROJECT" "module.s3_bucket.aws_s3_bucket_versioning.this[0]" "ferry-global-terraform-state"
import_resource "$PROJECT" "module.s3_bucket.aws_s3_bucket_server_side_encryption_configuration.this[0]" "ferry-global-terraform-state"
import_resource "$PROJECT" "module.s3_bucket.aws_s3_bucket_public_access_block.this[0]" "ferry-global-terraform-state"

echo "[1/4] backend: OK"
echo ""

# ---------------------------------------------------------------------------
# 2/4: ECR (container registry)
# ---------------------------------------------------------------------------

echo "[2/4] Importing ECR (container registry)..."
PROJECT="$IAC/global/cloud/aws/ecr"
terraform -chdir="$PROJECT" init -input=false -reconfigure > /dev/null 2>&1

import_resource "$PROJECT" "module.ecr_backend.aws_ecr_repository.this[0]" "lambda-ferry-backend"
import_resource "$PROJECT" "module.ecr_backend.aws_ecr_lifecycle_policy.this[0]" "lambda-ferry-backend"

echo "[2/4] ecr: OK"
echo ""

# ---------------------------------------------------------------------------
# 3/4: OIDC (GitHub Actions identity provider)
# ---------------------------------------------------------------------------

echo "[3/4] Importing OIDC (GitHub Actions OIDC provider)..."
PROJECT="$IAC/global/cloud/aws/oidc"
terraform -chdir="$PROJECT" init -input=false -reconfigure > /dev/null 2>&1

import_resource "$PROJECT" "aws_iam_openid_connect_provider.github" "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

echo "[3/4] oidc: OK"
echo ""

# ---------------------------------------------------------------------------
# 4/4: Shared (IAM roles, policies, secrets)
# ---------------------------------------------------------------------------

echo "[4/4] Importing shared (IAM + Secrets Manager)..."
PROJECT="$IAC/aws/staging/shared"
terraform -chdir="$PROJECT" init -input=false -reconfigure > /dev/null 2>&1

# --- Roles ---
import_resource "$PROJECT" "aws_iam_role.lambda_execution" "ferry-lambda-execution"
import_resource "$PROJECT" "aws_iam_role.gha_self_deploy" "ferry-gha-self-deploy"
import_resource "$PROJECT" "aws_iam_role.gha_dispatch" "ferry-gha-dispatch"

# --- Policies ---
import_resource "$PROJECT" "aws_iam_policy.lambda_dynamodb" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-dynamodb"
import_resource "$PROJECT" "aws_iam_policy.lambda_secrets" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-secrets"
import_resource "$PROJECT" "aws_iam_policy.lambda_logs" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-logs"
import_resource "$PROJECT" "aws_iam_policy.gha_ecr_auth" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-ecr-auth"
import_resource "$PROJECT" "aws_iam_policy.gha_self_deploy_ecr" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-self-deploy-ecr"
import_resource "$PROJECT" "aws_iam_policy.gha_self_deploy_lambda" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-self-deploy-lambda"
import_resource "$PROJECT" "aws_iam_policy.gha_dispatch_ecr" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-dispatch-ecr"
import_resource "$PROJECT" "aws_iam_policy.gha_dispatch_lambda" "arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-dispatch-lambda"

# --- Role-policy attachments ---
import_resource "$PROJECT" "aws_iam_role_policy_attachment.lambda_dynamodb" "ferry-lambda-execution/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-dynamodb"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.lambda_secrets" "ferry-lambda-execution/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-secrets"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.lambda_logs" "ferry-lambda-execution/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-lambda-logs"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_self_deploy_ecr_auth" "ferry-gha-self-deploy/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-ecr-auth"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_self_deploy_ecr" "ferry-gha-self-deploy/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-self-deploy-ecr"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_self_deploy_lambda" "ferry-gha-self-deploy/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-self-deploy-lambda"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_dispatch_ecr_auth" "ferry-gha-dispatch/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-ecr-auth"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_dispatch_ecr" "ferry-gha-dispatch/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-dispatch-ecr"
import_resource "$PROJECT" "aws_iam_role_policy_attachment.gha_dispatch_lambda" "ferry-gha-dispatch/arn:aws:iam::${ACCOUNT_ID}:policy/ferry-gha-dispatch-lambda"

# --- Secrets Manager ---
import_resource "$PROJECT" 'aws_secretsmanager_secret.github_app["app-id"]' "ferry/github-app/app-id"
import_resource "$PROJECT" 'aws_secretsmanager_secret.github_app["private-key"]' "ferry/github-app/private-key"
import_resource "$PROJECT" 'aws_secretsmanager_secret.github_app["webhook-secret"]' "ferry/github-app/webhook-secret"

echo "[4/4] shared: OK"
echo ""

# ---------------------------------------------------------------------------
# Validate: terraform plan should show no changes (or minimal drift)
# ---------------------------------------------------------------------------

echo "======================================="
echo "Import complete! Running terraform plan on each project to check drift..."
echo ""

for project_label in "global/cloud/aws/backend:backend" "global/cloud/aws/ecr:ecr" "global/cloud/aws/oidc:oidc" "aws/staging/shared:shared"; do
    dir="${project_label%%:*}"
    label="${project_label##*:}"
    echo "--- $label ---"
    terraform -chdir="$IAC/$dir" plan -input=false -detailed-exitcode 2>&1 | tail -3
    echo ""
done

echo "Done. Review any drift above and run 'terraform apply' to reconcile if needed."
