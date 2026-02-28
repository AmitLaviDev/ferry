output "bucket_arn" {
  description = "ARN of the Terraform state bucket"
  value       = aws_s3_bucket.state.arn
}

output "bucket_name" {
  description = "Name of the Terraform state bucket"
  value       = aws_s3_bucket.state.id
}

output "bucket_region" {
  description = "Region of the Terraform state bucket"
  value       = var.region
}
