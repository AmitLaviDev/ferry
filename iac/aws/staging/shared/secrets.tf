locals {
  github_app_secrets = {
    "app-id"         = "GitHub App ID for Ferry"
    "private-key"    = "GitHub App private key (PEM format) for Ferry"
    "webhook-secret" = "GitHub App webhook secret for Ferry"
  }
}

resource "aws_secretsmanager_secret" "github_app" {
  for_each = local.github_app_secrets

  name        = "ferry/github-app/${each.key}"
  description = each.value

  # MANUAL STEP: Values populated via CLI in Phase 14 after GitHub App registration
  # aws secretsmanager put-secret-value --secret-id ferry/github-app/<name> --secret-string "<value>"

  tags = {
    Component = "github-app"
  }
}
