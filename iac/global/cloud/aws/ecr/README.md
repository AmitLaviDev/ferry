# ecr

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.12.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 6.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 6.34.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_ecr_backend"></a> [ecr\_backend](#module\_ecr\_backend) | terraform-aws-modules/ecr/aws | 2.4.0 |

## Resources

| Name | Type |
|------|------|
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_region"></a> [region](#input\_region) | AWS region for the ECR repository | `string` | `"us-east-1"` | no |
| <a name="input_repository_name"></a> [repository\_name](#input\_repository\_name) | Name of the ECR repository for the Ferry backend Lambda | `string` | `"lambda-ferry-backend"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_registry_id"></a> [registry\_id](#output\_registry\_id) | AWS account ID (registry ID for ECR) |
| <a name="output_repository_arn"></a> [repository\_arn](#output\_repository\_arn) | ARN of the ECR repository |
| <a name="output_repository_name"></a> [repository\_name](#output\_repository\_name) | Name of the ECR repository |
| <a name="output_repository_url"></a> [repository\_url](#output\_repository\_url) | URL of the ECR repository |
<!-- END_TF_DOCS -->
