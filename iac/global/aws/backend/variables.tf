variable "bucket_name" {
  description = "Name of the S3 bucket for Terraform remote state"
  type        = string
  default     = "ferry-terraform-state"
}

variable "region" {
  description = "AWS region for the state bucket"
  type        = string
  default     = "us-east-1"
}
