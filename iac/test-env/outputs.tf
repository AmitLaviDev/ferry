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
