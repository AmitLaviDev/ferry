variable "repository_name" {
  description = "Name of the ECR repository for the Ferry backend Lambda"
  type        = string
  default     = "lambda-ferry-backend"
}

variable "region" {
  description = "AWS region for the ECR repository"
  type        = string
  default     = "us-east-1"
}
