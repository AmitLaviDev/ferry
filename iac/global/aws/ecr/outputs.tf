output "repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.backend.repository_url
}

output "repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.backend.arn
}

output "repository_name" {
  description = "Name of the ECR repository"
  value       = aws_ecr_repository.backend.name
}

output "registry_id" {
  description = "AWS account ID (registry ID for ECR)"
  value       = data.aws_caller_identity.current.account_id
}
