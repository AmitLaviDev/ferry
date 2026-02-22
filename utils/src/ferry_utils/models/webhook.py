"""Webhook event models for GitHub webhook payloads.

These models represent the minimal subset of GitHub webhook data
needed for Ferry's processing pipeline.
"""

from pydantic import BaseModel, ConfigDict


class WebhookHeaders(BaseModel):
    """Headers extracted from a GitHub webhook delivery."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    delivery_id: str
    signature: str


class Repository(BaseModel):
    """Minimal GitHub repository info from webhook payload."""

    model_config = ConfigDict(frozen=True)

    full_name: str
    default_branch: str


class Pusher(BaseModel):
    """GitHub user who triggered the push event."""

    model_config = ConfigDict(frozen=True)

    name: str


class PushEvent(BaseModel):
    """Minimal GitHub push event payload for Ferry processing."""

    model_config = ConfigDict(frozen=True)

    ref: str
    before: str
    after: str
    repository: Repository
    pusher: Pusher
