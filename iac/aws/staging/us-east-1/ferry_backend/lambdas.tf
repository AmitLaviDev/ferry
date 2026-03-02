module "backend" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.7.0"

  function_name           = var.lambda_function_name
  description             = "Ferry backend — receives GitHub webhooks via Function URL"
  create_role             = false
  lambda_role             = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
  create_package          = false
  package_type            = "Image"
  image_uri               = var.lambda_placeholder_image_uri
  ignore_source_code_hash = true
  memory_size             = var.lambda_memory_size
  timeout                 = var.lambda_timeout
  logging_log_format      = var.lambda_logging_log_format

  # Function URL for GitHub webhooks
  # Auth is NONE — the Lambda itself validates GitHub webhook signatures via HMAC
  create_lambda_function_url = true
  authorization_type         = "NONE"

  environment_variables = {
    FERRY_APP_ID_SECRET         = var.secret_name_app_id
    FERRY_PRIVATE_KEY_SECRET    = var.secret_name_private_key
    FERRY_WEBHOOK_SECRET_SECRET = var.secret_name_webhook_secret
    FERRY_TABLE_NAME            = module.dedup.dynamodb_table_id
    FERRY_LOG_LEVEL             = var.log_level
    FERRY_INSTALLATION_ID       = var.installation_id
  }

  tags = {
    Name = var.lambda_function_name
  }
}
