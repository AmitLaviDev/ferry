output "repository_url" {
  description = "URL of the ECR repository"
  value       = module.ecr_backend.repository_url
}

output "repository_arn" {
  description = "ARN of the ECR repository"
  value       = module.ecr_backend.repository_arn
}

output "repository_name" {
  description = "Name of the ECR repository"
  value       = module.ecr_backend.repository_name
}

output "registry_id" {
  description = "AWS account ID (registry ID for ECR)"
  value       = data.aws_caller_identity.current.account_id
}
