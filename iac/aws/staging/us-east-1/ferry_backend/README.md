# ferry_backend

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.12.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 6.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_terraform"></a> [terraform](#provider\_terraform) | n/a |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_backend"></a> [backend](#module\_backend) | terraform-aws-modules/lambda/aws | 8.7.0 |
| <a name="module_dedup"></a> [dedup](#module\_dedup) | terraform-aws-modules/dynamodb-table/aws | 5.5.0 |

## Resources

| Name | Type |
|------|------|
| [terraform_remote_state.shared](https://registry.terraform.io/providers/hashicorp/terraform/latest/docs/data-sources/remote_state) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_dynamodb_billing_mode"></a> [dynamodb\_billing\_mode](#input\_dynamodb\_billing\_mode) | DynamoDB billing mode | `string` | `"PAY_PER_REQUEST"` | no |
| <a name="input_dynamodb_table_name"></a> [dynamodb\_table\_name](#input\_dynamodb\_table\_name) | Name of the DynamoDB dedup table | `string` | `"ferry-webhook-dedup"` | no |
| <a name="input_installation_id"></a> [installation\_id](#input\_installation\_id) | GitHub App installation ID (placeholder until App registration) | `string` | `"113729879"` | no |
| <a name="input_lambda_function_name"></a> [lambda\_function\_name](#input\_lambda\_function\_name) | Name of the Ferry backend Lambda function | `string` | `"ferry-backend"` | no |
| <a name="input_lambda_logging_log_format"></a> [lambda\_logging\_log\_format](#input\_lambda\_logging\_log\_format) | Log format for Lambda function (JSON or Text) | `string` | `"JSON"` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | Amount of memory in MB for the Lambda function | `number` | `256` | no |
| <a name="input_lambda_placeholder_image_uri"></a> [lambda\_placeholder\_image\_uri](#input\_lambda\_placeholder\_image\_uri) | ECR image URI for initial Lambda deployment (placeholder image) | `string` | n/a | yes |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | Lambda function timeout in seconds | `number` | `30` | no |
| <a name="input_log_level"></a> [log\_level](#input\_log\_level) | Application log level for the Ferry backend Lambda | `string` | `"INFO"` | no |
| <a name="input_region"></a> [region](#input\_region) | AWS region | `string` | `"us-east-1"` | no |
| <a name="input_secret_name_app_id"></a> [secret\_name\_app\_id](#input\_secret\_name\_app\_id) | Secrets Manager name for the GitHub App ID | `string` | `"ferry/github-app/app-id"` | no |
| <a name="input_secret_name_private_key"></a> [secret\_name\_private\_key](#input\_secret\_name\_private\_key) | Secrets Manager name for the GitHub App private key | `string` | `"ferry/github-app/private-key"` | no |
| <a name="input_secret_name_webhook_secret"></a> [secret\_name\_webhook\_secret](#input\_secret\_name\_webhook\_secret) | Secrets Manager name for the GitHub App webhook secret | `string` | `"ferry/github-app/webhook-secret"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_dynamodb_table_arn"></a> [dynamodb\_table\_arn](#output\_dynamodb\_table\_arn) | ARN of the DynamoDB dedup table |
| <a name="output_dynamodb_table_name"></a> [dynamodb\_table\_name](#output\_dynamodb\_table\_name) | Name of the DynamoDB dedup table |
| <a name="output_lambda_cloudwatch_log_group_name"></a> [lambda\_cloudwatch\_log\_group\_name](#output\_lambda\_cloudwatch\_log\_group\_name) | Name of the CloudWatch log group |
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | ARN of the Lambda function |
| <a name="output_lambda_function_name"></a> [lambda\_function\_name](#output\_lambda\_function\_name) | Name of the Lambda function |
| <a name="output_lambda_function_url"></a> [lambda\_function\_url](#output\_lambda\_function\_url) | Public Function URL for the Ferry backend Lambda |
<!-- END_TF_DOCS -->
