# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/ferry-backend"
  retention_in_days = 30

  tags = {
    Name = "ferry-backend-logs"
  }
}

# -----------------------------------------------------------------------------
# DynamoDB Dedup Table
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "dedup" {
  name         = "ferry-webhook-dedup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Name = "ferry-webhook-dedup"
  }
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "backend" {
  function_name = "ferry-backend"
  role          = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 30

  environment {
    variables = {
      FERRY_APP_ID_SECRET         = "ferry/github-app/app-id"
      FERRY_PRIVATE_KEY_SECRET    = "ferry/github-app/private-key"
      FERRY_WEBHOOK_SECRET_SECRET = "ferry/github-app/webhook-secret"
      FERRY_TABLE_NAME            = aws_dynamodb_table.dedup.name
      FERRY_LOG_LEVEL             = var.log_level
      FERRY_INSTALLATION_ID       = var.installation_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.backend]

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name = "ferry-backend"
  }
}

# -----------------------------------------------------------------------------
# Lambda Function URL
# -----------------------------------------------------------------------------

resource "aws_lambda_function_url" "backend" {
  function_name      = aws_lambda_function.backend.function_name
  authorization_type = "NONE"
}
