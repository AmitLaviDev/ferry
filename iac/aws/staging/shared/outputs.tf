output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution IAM role"
  value       = aws_iam_role.lambda_execution.arn
}

output "lambda_execution_role_name" {
  description = "Name of the Lambda execution IAM role"
  value       = aws_iam_role.lambda_execution.name
}

output "gha_self_deploy_role_arn" {
  description = "ARN of the GHA self-deploy IAM role"
  value       = aws_iam_role.gha_self_deploy.arn
}

output "gha_dispatch_role_arn" {
  description = "ARN of the GHA dispatch IAM role"
  value       = aws_iam_role.gha_dispatch.arn
}

output "github_app_secret_arns" {
  description = "Map of GitHub App secret name to ARN"
  value       = { for k, v in aws_secretsmanager_secret.github_app : k => v.arn }
}
