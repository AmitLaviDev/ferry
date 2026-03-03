"""Tests for Secrets Manager resolution in settings.py.

Covers three modes:
1. Local dev: plain FERRY_* env vars, no SM calls
2. SM resolution: FERRY_*_SECRET env vars trigger SM lookups
3. Mixed: some fields from SM, some from direct env vars
"""

import boto3
from moto import mock_aws

# Required env vars for all settings instantiation
REQUIRED_ENV = {
    "FERRY_TABLE_NAME": "ferry-dedup-table",
    "FERRY_INSTALLATION_ID": "12345",
}


class TestLocalDevMode:
    """Test that Settings works with plain FERRY_* env vars (no SM)."""

    def test_loads_from_plain_env_vars(self, monkeypatch):
        """Local dev sets FERRY_APP_ID, FERRY_PRIVATE_KEY, FERRY_WEBHOOK_SECRET directly."""
        monkeypatch.setenv("FERRY_APP_ID", "test-app-id")
        monkeypatch.setenv("FERRY_PRIVATE_KEY", "test-private-key")
        monkeypatch.setenv("FERRY_WEBHOOK_SECRET", "test-webhook-secret")
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        # Ensure no _SECRET vars are set
        monkeypatch.delenv("FERRY_APP_ID_SECRET", raising=False)
        monkeypatch.delenv("FERRY_PRIVATE_KEY_SECRET", raising=False)
        monkeypatch.delenv("FERRY_WEBHOOK_SECRET_SECRET", raising=False)

        from ferry_backend.settings import Settings

        settings = Settings()

        assert settings.app_id == "test-app-id"
        assert settings.private_key == "test-private-key"
        assert settings.webhook_secret == "test-webhook-secret"
        assert settings.table_name == "ferry-dedup-table"
        assert settings.installation_id == 12345

    def test_strips_private_key_whitespace(self, monkeypatch):
        """field_validator strips whitespace from PEM keys in local dev mode."""
        monkeypatch.setenv("FERRY_APP_ID", "test-app-id")
        monkeypatch.setenv("FERRY_PRIVATE_KEY", "  \n test-key \n  ")
        monkeypatch.setenv("FERRY_WEBHOOK_SECRET", "test-secret")
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("FERRY_APP_ID_SECRET", raising=False)
        monkeypatch.delenv("FERRY_PRIVATE_KEY_SECRET", raising=False)
        monkeypatch.delenv("FERRY_WEBHOOK_SECRET_SECRET", raising=False)

        from ferry_backend.settings import Settings

        settings = Settings()
        assert settings.private_key == "test-key"


class TestSecretsManagerResolution:
    """Test that Settings resolves secrets from SM when FERRY_*_SECRET env vars are set."""

    @mock_aws
    def test_resolves_all_secrets_from_sm(self, monkeypatch):
        """All three secrets resolved from Secrets Manager."""
        # Set up SM secrets
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(
            Name="ferry/github-app/app-id",
            SecretString="sm-app-id-value",
        )
        client.create_secret(
            Name="ferry/github-app/private-key",
            SecretString="sm-private-key-value",
        )
        client.create_secret(
            Name="ferry/github-app/webhook-secret",
            SecretString="sm-webhook-secret-value",
        )

        # Set _SECRET env vars pointing to SM secret names
        monkeypatch.setenv("FERRY_APP_ID_SECRET", "ferry/github-app/app-id")
        monkeypatch.setenv("FERRY_PRIVATE_KEY_SECRET", "ferry/github-app/private-key")
        monkeypatch.setenv("FERRY_WEBHOOK_SECRET_SECRET", "ferry/github-app/webhook-secret")
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        # Plain values not set -- SM should populate them
        monkeypatch.delenv("FERRY_APP_ID", raising=False)
        monkeypatch.delenv("FERRY_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("FERRY_WEBHOOK_SECRET", raising=False)

        from ferry_backend.settings import Settings

        settings = Settings()

        assert settings.app_id == "sm-app-id-value"
        assert settings.private_key == "sm-private-key-value"
        assert settings.webhook_secret == "sm-webhook-secret-value"


class TestMixedMode:
    """Test mixed mode: some fields from SM, some from direct env vars."""

    @mock_aws
    def test_partial_sm_resolution(self, monkeypatch):
        """app_id from SM, private_key and webhook_secret from direct env vars."""
        # Set up only one SM secret
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(
            Name="ferry/github-app/app-id",
            SecretString="sm-app-id-value",
        )

        # app_id from SM, others from direct env vars
        monkeypatch.setenv("FERRY_APP_ID_SECRET", "ferry/github-app/app-id")
        monkeypatch.delenv("FERRY_APP_ID", raising=False)
        monkeypatch.setenv("FERRY_PRIVATE_KEY", "direct-private-key")
        monkeypatch.setenv("FERRY_WEBHOOK_SECRET", "direct-webhook-secret")
        monkeypatch.delenv("FERRY_PRIVATE_KEY_SECRET", raising=False)
        monkeypatch.delenv("FERRY_WEBHOOK_SECRET_SECRET", raising=False)
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        from ferry_backend.settings import Settings

        settings = Settings()

        assert settings.app_id == "sm-app-id-value"
        assert settings.private_key == "direct-private-key"
        assert settings.webhook_secret == "direct-webhook-secret"
