# -----------------------------------------------------------------------------
# Roles
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_execution" {
  name               = "ferry-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name = "ferry-lambda-execution"
  }
}

resource "aws_iam_role" "gha_self_deploy" {
  name               = "ferry-gha-self-deploy"
  assume_role_policy = data.aws_iam_policy_document.gha_self_deploy_assume_role.json

  tags = {
    Name = "ferry-gha-self-deploy"
  }
}

resource "aws_iam_role" "gha_dispatch" {
  name               = "ferry-gha-dispatch"
  assume_role_policy = data.aws_iam_policy_document.gha_dispatch_assume_role.json

  tags = {
    Name = "ferry-gha-dispatch"
  }
}

# -----------------------------------------------------------------------------
# Policies
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "lambda_dynamodb" {
  name   = "ferry-lambda-dynamodb"
  policy = data.aws_iam_policy_document.lambda_dynamodb.json

  tags = {
    Name = "ferry-lambda-dynamodb"
  }
}

resource "aws_iam_policy" "lambda_secrets" {
  name   = "ferry-lambda-secrets"
  policy = data.aws_iam_policy_document.lambda_secrets.json

  tags = {
    Name = "ferry-lambda-secrets"
  }
}

resource "aws_iam_policy" "lambda_logs" {
  name   = "ferry-lambda-logs"
  policy = data.aws_iam_policy_document.lambda_logs.json

  tags = {
    Name = "ferry-lambda-logs"
  }
}

resource "aws_iam_policy" "gha_ecr_auth" {
  name   = "ferry-gha-ecr-auth"
  policy = data.aws_iam_policy_document.gha_ecr_auth.json

  tags = {
    Name = "ferry-gha-ecr-auth"
  }
}

resource "aws_iam_policy" "gha_self_deploy_ecr" {
  name   = "ferry-gha-self-deploy-ecr"
  policy = data.aws_iam_policy_document.gha_self_deploy_ecr.json

  tags = {
    Name = "ferry-gha-self-deploy-ecr"
  }
}

resource "aws_iam_policy" "gha_self_deploy_lambda" {
  name   = "ferry-gha-self-deploy-lambda"
  policy = data.aws_iam_policy_document.gha_self_deploy_lambda.json

  tags = {
    Name = "ferry-gha-self-deploy-lambda"
  }
}

resource "aws_iam_policy" "gha_dispatch_ecr" {
  name   = "ferry-gha-dispatch-ecr"
  policy = data.aws_iam_policy_document.gha_dispatch_ecr.json

  tags = {
    Name = "ferry-gha-dispatch-ecr"
  }
}

resource "aws_iam_policy" "gha_dispatch_lambda" {
  name   = "ferry-gha-dispatch-lambda"
  policy = data.aws_iam_policy_document.gha_dispatch_lambda.json

  tags = {
    Name = "ferry-gha-dispatch-lambda"
  }
}

# -----------------------------------------------------------------------------
# Attachments: Lambda execution role
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_dynamodb.arn
}

resource "aws_iam_role_policy_attachment" "lambda_secrets" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_secrets.arn
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_logs.arn
}

# -----------------------------------------------------------------------------
# Attachments: GHA self-deploy role
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "gha_self_deploy_ecr_auth" {
  role       = aws_iam_role.gha_self_deploy.name
  policy_arn = aws_iam_policy.gha_ecr_auth.arn
}

resource "aws_iam_role_policy_attachment" "gha_self_deploy_ecr" {
  role       = aws_iam_role.gha_self_deploy.name
  policy_arn = aws_iam_policy.gha_self_deploy_ecr.arn
}

resource "aws_iam_role_policy_attachment" "gha_self_deploy_lambda" {
  role       = aws_iam_role.gha_self_deploy.name
  policy_arn = aws_iam_policy.gha_self_deploy_lambda.arn
}

# -----------------------------------------------------------------------------
# Attachments: GHA dispatch role
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "gha_dispatch_ecr_auth" {
  role       = aws_iam_role.gha_dispatch.name
  policy_arn = aws_iam_policy.gha_ecr_auth.arn
}

resource "aws_iam_role_policy_attachment" "gha_dispatch_ecr" {
  role       = aws_iam_role.gha_dispatch.name
  policy_arn = aws_iam_policy.gha_dispatch_ecr.arn
}

resource "aws_iam_role_policy_attachment" "gha_dispatch_lambda" {
  role       = aws_iam_role.gha_dispatch.name
  policy_arn = aws_iam_policy.gha_dispatch_lambda.arn
}
