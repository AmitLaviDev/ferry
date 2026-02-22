"""Backend Lambda configuration loaded from FERRY_* environment variables.

Uses pydantic-settings to validate types and fail fast on missing config.
Settings are loaded once at module level during Lambda cold start.
"""

from pydantic import field_validator
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
    """

    model_config = SettingsConfigDict(env_prefix="FERRY_")

    app_id: str
    private_key: str
    webhook_secret: str
    table_name: str
    installation_id: int
    log_level: str = "INFO"

    @field_validator("private_key")
    @classmethod
    def strip_private_key_whitespace(cls, v: str) -> str:
        """Strip surrounding whitespace from PEM keys.

        PEM keys stored in environment variables often have formatting
        issues from copy-paste or secret management systems.
        """
        return v.strip()
