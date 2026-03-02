module "dedup" {
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "5.5.0"

  name         = var.dynamodb_table_name
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "pk"
  range_key    = "sk"

  attributes = [
    { name = "pk", type = "S" },
    { name = "sk", type = "S" },
  ]

  ttl_enabled        = true
  ttl_attribute_name = "expires_at"

  tags = {
    Name = var.dynamodb_table_name
  }
}
