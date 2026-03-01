terraform {
  required_version = "~> 1.12.0"

  backend "s3" {
    bucket       = "ferry-global-terraform-state"
    key          = "global/aws/ecr/terraform.tfstate"
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

# No assume_role for global bootstrap resources -- uses ambient credentials.
# Per-environment TF projects will use assume_role.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Project   = "ferry"
    }
  }
}
