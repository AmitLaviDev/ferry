# -----------------------------------------------------------------------------
# Data sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "terraform_remote_state" "oidc" {
  backend = "s3"

  config = {
    bucket = "ferry-global-terraform-state"
    key    = "global/cloud/aws/oidc/terraform.tfstate"
    region = "us-east-1"
  }
}

# -----------------------------------------------------------------------------
# Trust policies: assume-role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_deploy_assume_role" {
  statement {
    sid     = "TestDeployOIDC"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.terraform_remote_state.oidc.outputs.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_owner}/${var.github_repo}:*"]
    }
  }
}

data "aws_iam_policy_document" "test_lambda_assume_role" {
  statement {
    sid     = "LambdaAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# -----------------------------------------------------------------------------
# Permission policies: ECR
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_ecr_auth" {
  statement {
    sid    = "ECRAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "test_ecr_push" {
  statement {
    sid    = "ECRPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:repository/${var.ecr_repository_name}",
    ]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: Lambda deploy
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_lambda_deploy" {
  statement {
    sid    = "LambdaDeploy"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:PublishVersion",
      "lambda:UpdateAlias",
      "lambda:CreateAlias",
      "lambda:GetAlias",
    ]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_function_name}",
    ]
  }
}
