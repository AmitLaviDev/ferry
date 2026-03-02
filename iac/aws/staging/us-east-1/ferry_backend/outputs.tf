output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = module.backend.lambda_function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = module.backend.lambda_function_arn
}

output "lambda_function_url" {
  description = "Public Function URL for the Ferry backend Lambda"
  value       = module.backend.lambda_function_url
}

output "lambda_cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = module.backend.lambda_cloudwatch_log_group_name
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB dedup table"
  value       = module.dedup.dynamodb_table_id
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB dedup table"
  value       = module.dedup.dynamodb_table_arn
}
