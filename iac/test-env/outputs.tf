output "test_deploy_role_arn" {
  description = "IAM role ARN for GHA runners in the test repo (set as AWS_ROLE_ARN secret)"
  value       = aws_iam_role.test_deploy.arn
}

output "ecr_repository_url" {
  description = "Full ECR repo URL for pushing test Lambda images"
  value       = module.ecr_test.repository_url
}

output "lambda_function_name" {
  description = "Lambda function name for verification"
  value       = module.test_lambda.lambda_function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.test_lambda.lambda_function_arn
}

output "state_machine_name" {
  description = "Step Functions state machine name"
  value       = aws_sfn_state_machine.test.name
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = aws_sfn_state_machine.test.arn
}

output "rest_api_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.test.id
}

output "rest_api_stage_url" {
  description = "API Gateway stage invoke URL"
  value       = aws_api_gateway_stage.test.invoke_url
}

output "apgw_invoke_role_arn" {
  description = "API Gateway invocation role ARN (for OpenAPI spec credentials)"
  value       = aws_iam_role.test_apgw_invoke.arn
}
