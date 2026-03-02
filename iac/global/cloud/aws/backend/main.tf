module "s3_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "4.10.0"

  bucket = var.bucket_name

  versioning = {
    enabled = true
  }

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm = "aws:kms"
      }
      bucket_key_enabled = true
    }
  }

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  tags = {
    Name    = var.bucket_name
    Purpose = "terraform-state"
  }
}
