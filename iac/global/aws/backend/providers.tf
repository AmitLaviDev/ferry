terraform {
  required_version = "~> 1.14"

  # NOTE: During initial bootstrap, run 'terraform init -backend=false' first,
  # then after apply, run 'terraform init -migrate-state -force-copy' to migrate to S3.
  backend "s3" {
    bucket       = "ferry-terraform-state"
    key          = "global/aws/backend/terraform.tfstate"
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

# No assume_role for this project -- it bootstraps itself with ambient credentials.
# All subsequent TF projects (ECR, IAM, app) use assume_role.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Project   = "ferry"
    }
  }
}
