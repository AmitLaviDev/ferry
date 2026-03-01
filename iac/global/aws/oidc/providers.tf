terraform {
  required_version = "~> 1.12.0"

  backend "s3" {
    bucket       = "ferry-global-terraform-state"
    key          = "global/aws/oidc/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# No assume_role for global resources -- uses ambient credentials.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Project   = "ferry"
    }
  }
}
