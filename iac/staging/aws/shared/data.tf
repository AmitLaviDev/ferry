# -----------------------------------------------------------------------------
# Data sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "terraform_remote_state" "oidc" {
  backend = "s3"

  config = {
    bucket = "ferry-global-terraform-state"
    key    = "global/aws/oidc/terraform.tfstate"
    region = "us-east-1"
  }
}

# -----------------------------------------------------------------------------
# Trust policy: Lambda execution role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
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
# Permission policies: Lambda execution role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_dynamodb" {
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = [
      "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/ferry-*",
    ]
  }
}

data "aws_iam_policy_document" "lambda_secrets" {
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:ferry/*",
    ]
  }
}

data "aws_iam_policy_document" "lambda_logs" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/ferry-*:*",
    ]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: GHA ECR auth (shared by both GHA roles)
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "gha_ecr_auth" {
  statement {
    sid    = "ECRAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: GHA self-deploy role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "gha_self_deploy_ecr" {
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
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/lambda-ferry-backend",
    ]
  }
}

data "aws_iam_policy_document" "gha_self_deploy_lambda" {
  statement {
    sid    = "LambdaUpdate"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
    ]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:ferry-backend",
    ]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: GHA dispatch role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "gha_dispatch_ecr" {
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
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/ferry/*",
    ]
  }
}

data "aws_iam_policy_document" "gha_dispatch_lambda" {
  statement {
    sid    = "LambdaUpdate"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
    ]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:ferry-*",
    ]
  }
}
