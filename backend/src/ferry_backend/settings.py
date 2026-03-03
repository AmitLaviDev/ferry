"""Backend Lambda configuration loaded from FERRY_* environment variables.

Uses pydantic-settings to validate types and fail fast on missing config.
Settings are loaded once at module level during Lambda cold start.

Secrets Manager resolution: When FERRY_*_SECRET env vars are present (Lambda
deployment), the corresponding secrets are resolved from AWS Secrets Manager
at cold start. When absent (local dev), plain FERRY_* env vars are used directly.
"""

import boto3
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ferry App Lambda configuration.

    All fields are loaded from FERRY_* environment variables:
    - FERRY_APP_ID: GitHub App ID (or Client ID)
    - FERRY_PRIVATE_KEY: PEM private key content
    - FERRY_WEBHOOK_SECRET: Webhook HMAC secret
    - FERRY_TABLE_NAME: DynamoDB table name for dedup
    - FERRY_INSTALLATION_ID: GitHub App installation ID
    - FERRY_LOG_LEVEL: Logging level (default: INFO)

    Secrets Manager resolution (Lambda deployment):
    - FERRY_APP_ID_SECRET: SM secret name for app_id
    - FERRY_PRIVATE_KEY_SECRET: SM secret name for private_key
    - FERRY_WEBHOOK_SECRET_SECRET: SM secret name for webhook_secret
    """

    model_config = SettingsConfigDict(env_prefix="FERRY_")

    app_id: str = ""
    private_key: str = ""
    webhook_secret: str = ""
    table_name: str
    installation_id: int
    log_level: str = "INFO"

    # Secrets Manager secret name env vars (optional -- absent in local dev)
    app_id_secret: str = ""
    private_key_secret: str = ""
    webhook_secret_secret: str = ""

    @field_validator("private_key")
    @classmethod
    def strip_private_key_whitespace(cls, v: str) -> str:
        """Strip surrounding whitespace from PEM keys.

        PEM keys stored in environment variables often have formatting
        issues from copy-paste or secret management systems.
        """
        return v.strip()

    @model_validator(mode="after")
    def resolve_secrets(self) -> "Settings":
        """Resolve Secrets Manager values when secret name env vars are present.

        Maps FERRY_*_SECRET env vars to their corresponding fields by calling
        AWS Secrets Manager get_secret_value for each non-empty secret name.
        Only creates a boto3 client if at least one secret needs resolution.
        """
        secret_map = {
            "app_id_secret": "app_id",
            "private_key_secret": "private_key",
            "webhook_secret_secret": "webhook_secret",
        }
        names_to_resolve = {
            field: getattr(self, source)
            for source, field in secret_map.items()
            if getattr(self, source)
        }
        if not names_to_resolve:
            return self
        client = boto3.client("secretsmanager", region_name="us-east-1")
        for field, secret_name in names_to_resolve.items():
            resp = client.get_secret_value(SecretId=secret_name)
            object.__setattr__(self, field, resp["SecretString"])
        return self
