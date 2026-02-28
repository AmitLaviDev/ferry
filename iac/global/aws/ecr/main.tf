data "aws_caller_identity" "current" {}

module "ecr_backend" {
  source  = "terraform-aws-modules/ecr/aws"
  version = "2.4.0"

  repository_name                 = var.repository_name
  repository_image_tag_mutability = "MUTABLE"
  repository_force_delete         = false
  repository_image_scan_on_push   = true

  create_lifecycle_policy = true
  repository_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })

  tags = {
    Name = var.repository_name
  }
}
