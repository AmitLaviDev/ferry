"""Ferry shared error types."""


class FerryError(Exception):
    """Base error for all Ferry exceptions."""


class WebhookValidationError(FerryError):
    """Webhook HMAC-SHA256 signature validation failed."""


class DuplicateDeliveryError(FerryError):
    """Duplicate webhook delivery detected (used for flow control logging, not a true error)."""


class GitHubAuthError(FerryError):
    """GitHub App JWT generation or installation token exchange failed."""


class ConfigError(FerryError):
    """ferry.yaml parsing or validation failed (Phase 2+)."""


class BuildError(FerryError):
    """Container image build or push failed."""


class DeployError(FerryError):
    """AWS resource deployment failed (Lambda, Step Functions, API Gateway)."""
