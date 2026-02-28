output "bucket_arn" {
  description = "ARN of the Terraform state bucket"
  value       = module.s3_bucket.s3_bucket_arn
}

output "bucket_name" {
  description = "Name of the Terraform state bucket"
  value       = module.s3_bucket.s3_bucket_id
}

output "bucket_region" {
  description = "Region of the Terraform state bucket"
  value       = var.region
}
