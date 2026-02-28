#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Ferry Bootstrap Script
#
# Orchestrates the full Phase 11 setup sequence:
#   1. Create S3 state backend (chicken-and-egg: local init -> apply -> migrate)
#   2. Create ECR repository via Terraform
#   3. Build and push placeholder Lambda image to ECR
#
# Idempotent: re-running skips already-completed steps.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUCKET_NAME="ferry-terraform-state"
ECR_REPO="lambda-ferry-backend"
AWS_REGION="us-east-1"
PLACEHOLDER_TAG="placeholder"

BACKEND_DIR="$REPO_ROOT/iac/global/aws/backend"
ECR_DIR="$REPO_ROOT/iac/global/aws/ecr"

# Track which step we're in for the error trap
CURRENT_STEP=""

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_bold=""
_reset=""
_red=""
_green=""
_yellow=""

if [[ -t 1 ]] && command -v tput &>/dev/null; then
  _bold=$(tput bold 2>/dev/null || true)
  _reset=$(tput sgr0 2>/dev/null || true)
  _red=$(tput setaf 1 2>/dev/null || true)
  _green=$(tput setaf 2 2>/dev/null || true)
  _yellow=$(tput setaf 3 2>/dev/null || true)
fi

log_step() {
  echo ""
  echo "${_bold}==> $1${_reset}"
}

log_info() {
  echo "    $1"
}

log_skip() {
  echo "    ${_yellow}[skip]${_reset} $1"
}

log_success() {
  echo "    ${_green}[done]${_reset} $1"
}

log_error() {
  echo "${_red}ERROR:${_reset} $1" >&2
}

# ---------------------------------------------------------------------------
# Error trap
# ---------------------------------------------------------------------------

on_error() {
  local exit_code=$?
  log_error "Bootstrap failed during step: ${CURRENT_STEP:-unknown}"
  log_error "Exit code: $exit_code"
  exit "$exit_code"
}

trap on_error ERR

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

check_prerequisites() {
  CURRENT_STEP="prerequisites"
  log_step "Checking prerequisites"

  local missing=0

  if ! command -v terraform &>/dev/null; then
    log_error "terraform is not installed. See: https://developer.hashicorp.com/terraform/install"
    missing=1
  else
    log_info "terraform: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"
  fi

  if ! command -v aws &>/dev/null; then
    log_error "aws CLI is not installed. See: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    missing=1
  else
    log_info "aws: $(aws --version 2>&1 | head -1)"
  fi

  if ! command -v docker &>/dev/null; then
    log_error "docker is not installed. See: https://docs.docker.com/get-docker/"
    missing=1
  else
    log_info "docker: $(docker --version)"
  fi

  if [[ $missing -ne 0 ]]; then
    log_error "Missing required tools. Install them and re-run."
    exit 1
  fi

  log_info ""
  log_info "Verifying AWS credentials..."
  local caller_identity
  if ! caller_identity=$(aws sts get-caller-identity --output json 2>&1); then
    log_error "AWS credentials are not configured or have expired."
    log_error "Run 'aws configure' or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN."
    exit 1
  fi

  local account_id arn
  account_id=$(echo "$caller_identity" | python3 -c 'import sys,json; print(json.load(sys.stdin)["Account"])')
  arn=$(echo "$caller_identity" | python3 -c 'import sys,json; print(json.load(sys.stdin)["Arn"])')
  log_info "Account: $account_id"
  log_info "Caller:  $arn"
}

# ---------------------------------------------------------------------------
# Step 1: Bootstrap S3 state backend
# ---------------------------------------------------------------------------

step_backend() {
  CURRENT_STEP="S3 state backend"
  log_step "Step 1: S3 state backend"

  local bucket_exists=false
  if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    bucket_exists=true
  fi

  local state_is_remote=false
  local tfstate_file="$BACKEND_DIR/.terraform/terraform.tfstate"
  if [[ -f "$tfstate_file" ]] && grep -q '"type": "s3"' "$tfstate_file" 2>/dev/null; then
    state_is_remote=true
  fi

  if $bucket_exists && $state_is_remote; then
    log_skip "S3 bucket '$BUCKET_NAME' exists and state is already remote"
    return
  fi

  if ! $bucket_exists; then
    log_info "Creating S3 bucket '$BUCKET_NAME'..."
    log_info "Initializing Terraform with local backend (bucket doesn't exist yet)..."
    terraform -chdir="$BACKEND_DIR" init -backend=false -input=false
    log_info "Applying Terraform to create S3 bucket..."
    terraform -chdir="$BACKEND_DIR" apply -auto-approve -input=false
    log_success "S3 bucket '$BUCKET_NAME' created"
  else
    log_info "S3 bucket '$BUCKET_NAME' already exists"
  fi

  if ! $state_is_remote; then
    log_info "Migrating Terraform state to S3 backend..."
    terraform -chdir="$BACKEND_DIR" init -migrate-state -force-copy -input=false
    log_success "State migrated to S3"
  fi
}

# ---------------------------------------------------------------------------
# Step 2: Create ECR repository
# ---------------------------------------------------------------------------

step_ecr() {
  CURRENT_STEP="ECR repository"
  log_step "Step 2: ECR repository"

  if aws ecr describe-repositories \
       --repository-names "$ECR_REPO" \
       --region "$AWS_REGION" &>/dev/null; then
    log_skip "ECR repository '$ECR_REPO' already exists"
    return
  fi

  log_info "Creating ECR repository '$ECR_REPO'..."
  terraform -chdir="$ECR_DIR" init -input=false
  terraform -chdir="$ECR_DIR" apply -auto-approve -input=false
  log_success "ECR repository '$ECR_REPO' created"
}

# ---------------------------------------------------------------------------
# Step 3: Build and push placeholder image
# ---------------------------------------------------------------------------

step_placeholder() {
  CURRENT_STEP="placeholder image"
  log_step "Step 3: Placeholder Lambda image"

  if aws ecr describe-images \
       --repository-name "$ECR_REPO" \
       --image-ids imageTag="$PLACEHOLDER_TAG" \
       --region "$AWS_REGION" &>/dev/null; then
    log_skip "Placeholder image '$ECR_REPO:$PLACEHOLDER_TAG' already exists in ECR"
    return
  fi

  local account_id
  account_id=$(aws sts get-caller-identity --query Account --output text)
  local ecr_registry="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  local ecr_uri="${ecr_registry}/${ECR_REPO}"

  log_info "Logging in to ECR..."
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ecr_registry"

  log_info "Building placeholder image (arm64)..."
  docker build \
    --platform linux/arm64 \
    -t "${ecr_uri}:${PLACEHOLDER_TAG}" \
    "$REPO_ROOT/iac/resources/placeholders/ecr_image"

  log_info "Pushing placeholder image..."
  docker push "${ecr_uri}:${PLACEHOLDER_TAG}"

  log_success "Placeholder image pushed to ${ecr_uri}:${PLACEHOLDER_TAG}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  log_step "Ferry Bootstrap"
  log_info "Repo root: $REPO_ROOT"

  check_prerequisites
  step_backend
  step_ecr
  step_placeholder

  log_step "Bootstrap complete"
  echo ""
  log_info "Resources created/verified:"
  log_info "  - S3 bucket:     $BUCKET_NAME"
  log_info "  - ECR repo:      $ECR_REPO"
  log_info "  - Placeholder:   $ECR_REPO:$PLACEHOLDER_TAG"
  echo ""
}

main "$@"
