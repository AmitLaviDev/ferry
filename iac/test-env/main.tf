# -----------------------------------------------------------------------------
# ECR Repository
# -----------------------------------------------------------------------------

module "ecr_test" {
  source  = "terraform-aws-modules/ecr/aws"
  version = "2.4.0"

  repository_name                 = var.ecr_repository_name
  repository_image_tag_mutability = "MUTABLE"
  repository_force_delete         = false
  repository_image_scan_on_push   = true

  create_lifecycle_policy = true
  repository_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })

  repository_lambda_read_access_arns = [module.test_lambda.lambda_function_arn]

  tags = {
    Name = var.ecr_repository_name
  }
}

# -----------------------------------------------------------------------------
# IAM Role: Test deploy (OIDC trust for GHA runners in test repo)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_deploy" {
  name               = "ferry-test-deploy"
  assume_role_policy = data.aws_iam_policy_document.test_deploy_assume_role.json

  tags = {
    Name = "ferry-test-deploy"
  }
}

resource "aws_iam_policy" "test_ecr_auth" {
  name   = "ferry-test-ecr-auth"
  policy = data.aws_iam_policy_document.test_ecr_auth.json

  tags = {
    Name = "ferry-test-ecr-auth"
  }
}

resource "aws_iam_policy" "test_ecr_push" {
  name   = "ferry-test-ecr-push"
  policy = data.aws_iam_policy_document.test_ecr_push.json

  tags = {
    Name = "ferry-test-ecr-push"
  }
}

resource "aws_iam_policy" "test_lambda_deploy" {
  name   = "ferry-test-lambda-deploy"
  policy = data.aws_iam_policy_document.test_lambda_deploy.json

  tags = {
    Name = "ferry-test-lambda-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_ecr_auth" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_ecr_auth.arn
}

resource "aws_iam_role_policy_attachment" "test_ecr_push" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_ecr_push.arn
}

resource "aws_iam_role_policy_attachment" "test_lambda_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_lambda_deploy.arn
}

# -----------------------------------------------------------------------------
# Deploy role: Step Functions deploy permissions
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "test_sf_deploy" {
  name   = "ferry-test-sf-deploy"
  policy = data.aws_iam_policy_document.test_sf_deploy.json

  tags = {
    Name = "ferry-test-sf-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_sf_deploy.arn
}

# -----------------------------------------------------------------------------
# Deploy role: API Gateway deploy permissions
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "test_apgw_deploy" {
  name   = "ferry-test-apgw-deploy"
  policy = data.aws_iam_policy_document.test_apgw_deploy.json

  tags = {
    Name = "ferry-test-apgw-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_apgw_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_apgw_deploy.arn
}

# -----------------------------------------------------------------------------
# IAM Role: Test Lambda execution (minimal, just for the Lambda to run)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_lambda_execution" {
  name               = "ferry-test-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.test_lambda_assume_role.json

  tags = {
    Name = "ferry-test-lambda-execution"
  }
}

resource "aws_iam_role_policy_attachment" "test_lambda_basic_execution" {
  role       = aws_iam_role.test_lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "test_lambda_ecr_pull" {
  name   = "ferry-test-lambda-ecr-pull"
  policy = data.aws_iam_policy_document.test_lambda_ecr_pull.json

  tags = {
    Name = "ferry-test-lambda-ecr-pull"
  }
}

resource "aws_iam_role_policy_attachment" "test_lambda_ecr_pull" {
  role       = aws_iam_role.test_lambda_execution.name
  policy_arn = aws_iam_policy.test_lambda_ecr_pull.arn
}

# -----------------------------------------------------------------------------
# Lambda Function: Test hello-world (pre-created for E2E validation)
# -----------------------------------------------------------------------------

module "test_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.7.0"

  function_name           = var.lambda_function_name
  description             = "Ferry test hello-world Lambda -- pre-created for E2E validation"
  create_role             = false
  lambda_role             = aws_iam_role.test_lambda_execution.arn
  create_package          = false
  package_type            = "Image"
  image_uri               = var.lambda_placeholder_image_uri
  ignore_source_code_hash = true
  memory_size             = 128
  timeout                 = 30
  architectures           = ["x86_64"]

  create_lambda_function_url = false

  tags = {
    Name = var.lambda_function_name
  }
}
