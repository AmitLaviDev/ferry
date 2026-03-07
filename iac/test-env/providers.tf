terraform {
  required_version = "~> 1.12.0"

  backend "s3" {
    bucket       = "ferry-global-terraform-state"
    key          = "test-env/terraform.tfstate"
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

# No assume_role -- uses ambient credentials (same pattern as global TF projects)
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Project   = "ferry-test"
    }
  }
}
