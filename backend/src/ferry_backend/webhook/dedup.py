"""DynamoDB dual-key deduplication for webhook deliveries.

Deduplicates on two levels:
1. Delivery-level: Catches GitHub retries (same X-GitHub-Delivery header)
2. Event-level: Catches re-queued events with new delivery IDs but same content
   (e.g., push to same repo+SHA)

Uses DynamoDB conditional writes (attribute_not_exists) for atomic check-and-write.
ConditionalCheckFailedException is the expected signal for duplicates, not an error.

Reference: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html
"""

import time

from botocore.exceptions import ClientError

TTL_SECONDS = 86400  # 24 hours


def is_duplicate(
    delivery_id: str,
    payload: dict,
    table_name: str,
    client: object,
) -> bool:
    """Check if a webhook delivery is a duplicate.

    Performs dual-key dedup: delivery-level first (most common),
    then event-level (catches re-queued events with new delivery IDs).

    Args:
        delivery_id: GitHub X-GitHub-Delivery header value.
        payload: Parsed webhook event payload.
        table_name: DynamoDB table name.
        client: boto3 DynamoDB client.

    Returns:
        True if duplicate (should skip processing), False if new.
    """
    now = int(time.time())
    expires_at = now + TTL_SECONDS

    # Try delivery-level dedup first (most common case)
    if not _try_record(client, table_name, f"DELIVERY#{delivery_id}", expires_at):
        return True  # Duplicate delivery

    # Try event-level dedup (catches re-queued events with new delivery IDs)
    event_key = _build_event_key(payload)
    return bool(event_key and not _try_record(client, table_name, event_key, expires_at))


def _try_record(client: object, table_name: str, pk: str, expires_at: int) -> bool:
    """Attempt conditional write. Returns True if new, False if duplicate.

    Args:
        client: boto3 DynamoDB client.
        table_name: DynamoDB table name.
        pk: Partition key value.
        expires_at: TTL timestamp (seconds since epoch).

    Returns:
        True if record was created (new), False if already exists (duplicate).
    """
    try:
        client.put_item(
            TableName=table_name,
            Item={
                "pk": {"S": pk},
                "sk": {"S": "METADATA"},
                "expires_at": {"N": str(expires_at)},
                "created_at": {"N": str(int(time.time()))},
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True  # New record
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False  # Duplicate
        raise  # Unexpected error, propagate


def _build_event_key(payload: dict) -> str | None:
    """Build event-level dedup key from webhook event payload.

    For pull_request events: EVENT#pull_request#{repo}#{number}#{head_sha}
    For push events: EVENT#push#{repo_full_name}#{after_sha}

    The pull_request check comes first because PR payloads also contain
    ``repository`` and ``after`` fields that would match the push pattern.

    Args:
        payload: Parsed webhook event payload.

    Returns:
        Dedup key string, or None if payload lacks required fields.
    """
    # Check for pull_request FIRST (discriminator)
    pr = payload.get("pull_request")
    if pr is not None:
        repo = payload.get("repository", {}).get("full_name")
        number = pr.get("number")
        head_sha = pr.get("head", {}).get("sha")
        if repo and number is not None and head_sha:
            return f"EVENT#pull_request#{repo}#{number}#{head_sha}"
        return None

    # Push event fallback
    repo = payload.get("repository", {}).get("full_name")
    after_sha = payload.get("after")
    if repo and after_sha:
        return f"EVENT#push#{repo}#{after_sha}"
    return None
