# -----------------------------------------------------------------------------
# IAM Role: API Gateway invocation (StartExecution)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_apgw_invoke" {
  name               = "ferry-test-apgw-invoke"
  assume_role_policy = data.aws_iam_policy_document.test_apgw_assume_role.json

  tags = {
    Name = "ferry-test-apgw-invoke"
  }
}

resource "aws_iam_policy" "test_apgw_start_execution" {
  name   = "ferry-test-apgw-start-execution"
  policy = data.aws_iam_policy_document.test_apgw_start_execution.json

  tags = {
    Name = "ferry-test-apgw-start-execution"
  }
}

resource "aws_iam_role_policy_attachment" "test_apgw_start_execution" {
  role       = aws_iam_role.test_apgw_invoke.name
  policy_arn = aws_iam_policy.test_apgw_start_execution.arn
}

# -----------------------------------------------------------------------------
# API Gateway REST API
# -----------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "test" {
  name        = var.apigw_name
  description = "Ferry test API -- spec managed by Ferry deploy"

  body = jsonencode({
    openapi = "3.0.1"
    info = {
      title   = var.apigw_name
      version = "1.0"
    }
    paths = {}
  })

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  lifecycle {
    ignore_changes = [body]
  }

  tags = {
    Name = var.apigw_name
  }
}

resource "aws_api_gateway_deployment" "test" {
  rest_api_id = aws_api_gateway_rest_api.test.id
  description = "Initial placeholder deployment"

  triggers = {
    redeployment = sha1(jsonencode(aws_api_gateway_rest_api.test.body))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "test" {
  deployment_id = aws_api_gateway_deployment.test.id
  rest_api_id   = aws_api_gateway_rest_api.test.id
  stage_name    = "test"

  tags = {
    Name = "${var.apigw_name}-test"
  }
}
