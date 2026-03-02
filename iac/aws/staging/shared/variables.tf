variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "github_org" {
  description = "GitHub organization name for OIDC trust policy scoping"
  type        = string
  default     = "get-ferry"
}

variable "github_repo" {
  description = "GitHub repository name for self-deploy OIDC trust policy"
  type        = string
  default     = "ferry"
}
