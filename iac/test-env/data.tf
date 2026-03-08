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
# Permission policies: Lambda execution (ECR pull for container image)
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_lambda_ecr_pull" {
  statement {
    sid    = "ECRPull"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:repository/${var.ecr_repository_name}",
    ]
  }

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
# Permission policies: Lambda deploy
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_lambda_deploy" {
  statement {
    sid    = "LambdaDeploy"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:PublishVersion",
      "lambda:UpdateAlias",
      "lambda:CreateAlias",
      "lambda:GetAlias",
    ]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_function_name}",
      "arn:aws:lambda:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_function_name}:*",
    ]
  }
}

# -----------------------------------------------------------------------------
# Trust policies: SF and APGW
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_sf_assume_role" {
  statement {
    sid     = "StepFunctionsAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "test_apgw_assume_role" {
  statement {
    sid     = "APIGatewayAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

# -----------------------------------------------------------------------------
# Permission policies: SF execution
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_sf_invoke_lambda" {
  statement {
    sid     = "InvokeLambda"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      module.test_lambda.lambda_function_arn,
      "${module.test_lambda.lambda_function_arn}:*",
    ]
  }
}

data "aws_iam_policy_document" "test_sf_logs" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: APGW invocation
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_apgw_start_execution" {
  statement {
    sid       = "StartExecution"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [module.step_function.state_machine_arn]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: Deploy role SF
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_sf_deploy" {
  statement {
    sid    = "StepFunctionsDeploy"
    effect = "Allow"
    actions = [
      "states:UpdateStateMachine",
      "states:DescribeStateMachine",
      "states:TagResource",
      "states:ListTagsForResource",
    ]
    resources = [module.step_function.state_machine_arn]
  }
}

# -----------------------------------------------------------------------------
# Permission policies: Deploy role APGW
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "test_apgw_deploy" {
  statement {
    sid    = "APIGatewayDeploy"
    effect = "Allow"
    actions = [
      "apigateway:PutRestApi",
      "apigateway:CreateDeployment",
      "apigateway:GetRestApi",
      "apigateway:GetTags",
      "apigateway:TagResource",
    ]
    resources = [
      "arn:aws:apigateway:${data.aws_region.current.id}::/restapis/${aws_api_gateway_rest_api.test.id}",
      "arn:aws:apigateway:${data.aws_region.current.id}::/restapis/${aws_api_gateway_rest_api.test.id}/*",
    ]
  }
}
