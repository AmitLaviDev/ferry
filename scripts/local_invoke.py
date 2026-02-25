"""Manually invoke the Phase 1 handler with a simulated GitHub push webhook.

Usage:
    uv run python scripts/local_invoke.py

Demonstrates the full flow: signature validation → dedup → accepted.
Run it twice to see dedup in action.
"""

import hashlib
import hmac
import json
import os
import uuid

# Set env vars BEFORE any imports that trigger Settings
SECRET = "test-webhook-secret-123"
os.environ.update({
    "FERRY_APP_ID": "12345",
    "FERRY_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
    "FERRY_WEBHOOK_SECRET": SECRET,
    "FERRY_TABLE_NAME": "ferry-dedup-test",
    "FERRY_INSTALLATION_ID": "67890",
    "FERRY_LOG_LEVEL": "DEBUG",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
})

import boto3
from moto import mock_aws


def make_event(body_dict: dict, event_type: str = "push", delivery_id: str | None = None) -> dict:
    """Build a Lambda Function URL event with proper HMAC signature."""
    body = json.dumps(body_dict)
    sig = "sha256=" + hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return {
        "headers": {
            "x-hub-signature-256": sig,
            "x-github-event": event_type,
            "x-github-delivery": delivery_id or str(uuid.uuid4()),
        },
        "body": body,
        "isBase64Encoded": False,
    }


PUSH_PAYLOAD = {
    "ref": "refs/heads/main",
    "before": "abc1234" * 5 + "abcde",
    "after": "def5678" * 5 + "defgh",
    "repository": {
        "full_name": "myorg/myrepo",
        "default_branch": "main",
    },
    "pusher": {"name": "developer"},
}


@mock_aws
def main():
    # Create the DynamoDB table that dedup expects
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="ferry-dedup-test",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # Import handler AFTER moto is active
    from ferry_backend.webhook.handler import handler

    delivery = str(uuid.uuid4())

    # --- Test 1: Valid push → accepted ---
    print("=" * 60)
    print("TEST 1: Valid push event")
    print("=" * 60)
    event = make_event(PUSH_PAYLOAD, delivery_id=delivery)
    result = handler(event, None)
    print(f"Status: {result['statusCode']}")
    print(f"Body:   {result['body']}")
    print()

    # --- Test 2: Same delivery ID → duplicate ---
    print("=" * 60)
    print("TEST 2: Replay same delivery (dedup)")
    print("=" * 60)
    event = make_event(PUSH_PAYLOAD, delivery_id=delivery)
    result = handler(event, None)
    print(f"Status: {result['statusCode']}")
    print(f"Body:   {result['body']}")
    print()

    # --- Test 3: Bad signature → 401 ---
    print("=" * 60)
    print("TEST 3: Invalid signature")
    print("=" * 60)
    event = make_event(PUSH_PAYLOAD)
    event["headers"]["x-hub-signature-256"] = "sha256=badbadbadbad"
    result = handler(event, None)
    print(f"Status: {result['statusCode']}")
    print(f"Body:   {result['body']}")
    print()

    # --- Test 4: Non-push event → ignored ---
    print("=" * 60)
    print("TEST 4: Non-push event (issues)")
    print("=" * 60)
    event = make_event({"action": "opened"}, event_type="issues")
    result = handler(event, None)
    print(f"Status: {result['statusCode']}")
    print(f"Body:   {result['body']}")
    print()

    print("All manual tests complete.")


if __name__ == "__main__":
    main()
