variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "log_level" {
  description = "Log level for the Ferry backend Lambda"
  type        = string
  default     = "INFO"
}

variable "installation_id" {
  description = "GitHub App installation ID (placeholder until App registration in Phase 14)"
  type        = string
  default     = "0"
}
