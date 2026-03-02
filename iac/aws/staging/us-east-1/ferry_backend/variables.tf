variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# --- Lambda ---

variable "lambda_function_name" {
  description = "Name of the Ferry backend Lambda function"
  type        = string
  default     = "ferry-backend"
}

variable "lambda_placeholder_image_uri" {
  description = "ECR image URI for initial Lambda deployment (placeholder image)"
  type        = string
}

variable "lambda_memory_size" {
  description = "Amount of memory in MB for the Lambda function"
  type        = number
  default     = 256
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_logging_log_format" {
  description = "Log format for Lambda function (JSON or Text)"
  type        = string
  default     = "JSON"
}

variable "log_level" {
  description = "Application log level for the Ferry backend Lambda"
  type        = string
  default     = "INFO"
}

variable "installation_id" {
  description = "GitHub App installation ID (placeholder until App registration)"
  type        = string
  default     = "0"
}

# --- Secrets ---

variable "secret_name_app_id" {
  description = "Secrets Manager name for the GitHub App ID"
  type        = string
  default     = "ferry/github-app/app-id"
}

variable "secret_name_private_key" {
  description = "Secrets Manager name for the GitHub App private key"
  type        = string
  default     = "ferry/github-app/private-key"
}

variable "secret_name_webhook_secret" {
  description = "Secrets Manager name for the GitHub App webhook secret"
  type        = string
  default     = "ferry/github-app/webhook-secret"
}

# --- DynamoDB ---

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB dedup table"
  type        = string
  default     = "ferry-webhook-dedup"
}

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode"
  type        = string
  default     = "PAY_PER_REQUEST"
}
