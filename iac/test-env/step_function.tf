# -----------------------------------------------------------------------------
# IAM Role: Step Functions execution
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_sf_execution" {
  name               = "ferry-test-sf-execution"
  assume_role_policy = data.aws_iam_policy_document.test_sf_assume_role.json

  tags = {
    Name = "ferry-test-sf-execution"
  }
}

resource "aws_iam_policy" "test_sf_invoke_lambda" {
  name   = "ferry-test-sf-invoke-lambda"
  policy = data.aws_iam_policy_document.test_sf_invoke_lambda.json

  tags = {
    Name = "ferry-test-sf-invoke-lambda"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_invoke_lambda" {
  role       = aws_iam_role.test_sf_execution.name
  policy_arn = aws_iam_policy.test_sf_invoke_lambda.arn
}

resource "aws_iam_policy" "test_sf_logs" {
  name   = "ferry-test-sf-logs"
  policy = data.aws_iam_policy_document.test_sf_logs.json

  tags = {
    Name = "ferry-test-sf-logs"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_logs" {
  role       = aws_iam_role.test_sf_execution.name
  policy_arn = aws_iam_policy.test_sf_logs.arn
}

# -----------------------------------------------------------------------------
# Step Functions State Machine
# -----------------------------------------------------------------------------

module "step_function" {
  source  = "terraform-aws-modules/step-functions/aws"
  version = "5.1.0"

  name = var.sf_name
  type = "STANDARD"

  definition = jsonencode({
    Comment = "Placeholder -- overwritten by Ferry deploy"
    StartAt = "Placeholder"
    States = {
      Placeholder = {
        Type = "Pass"
        End  = true
      }
    }
  })

  create_role       = false
  use_existing_role = true
  role_arn          = aws_iam_role.test_sf_execution.arn

  tags = {
    Name = var.sf_name
  }
}
