output "function_url" {
  description = "Public Function URL for the Ferry backend Lambda"
  value       = aws_lambda_function_url.backend.function_url
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB dedup table"
  value       = aws_dynamodb_table.dedup.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB dedup table"
  value       = aws_dynamodb_table.dedup.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.backend.name
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.backend.function_name
}
