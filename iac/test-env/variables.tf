variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "github_owner" {
  description = "GitHub owner for OIDC trust policy"
  type        = string
  default     = "AmitLaviDev"
}

variable "github_repo" {
  description = "GitHub repo name for OIDC trust policy"
  type        = string
  default     = "ferry-test-app"
}

variable "ecr_repository_name" {
  description = "ECR repo name for test Lambda"
  type        = string
  default     = "ferry-test/hello-world"
}

variable "lambda_function_name" {
  description = "Lambda function name for test Lambda"
  type        = string
  default     = "ferry-test-hello-world"
}

variable "lambda_placeholder_image_uri" {
  description = "Placeholder image URI from ECR -- set after first ECR push or use public.ecr.aws/lambda/python:3.12"
  type        = string
}
