data "terraform_remote_state" "shared" {
  backend = "s3"

  config = {
    bucket = "ferry-global-terraform-state"
    key    = "aws/staging/shared/terraform.tfstate"
    region = "us-east-1"
  }
}

data "terraform_remote_state" "ecr" {
  backend = "s3"

  config = {
    bucket = "ferry-global-terraform-state"
    key    = "global/cloud/aws/ecr/terraform.tfstate"
    region = "us-east-1"
  }
}
