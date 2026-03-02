resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # thumbprint_list is optional since AWS provider v5.81.0
  # AWS validates GitHub OIDC via its root CA library (since July 2023)

  tags = {
    Name = "github-actions"
  }
}
