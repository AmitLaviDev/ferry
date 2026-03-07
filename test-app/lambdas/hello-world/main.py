"""Hello world Lambda handler for Ferry E2E testing."""

import json


def handler(event, context):
    """Return a simple greeting response.

    This is the minimal handler needed to verify Ferry's
    push-to-deploy loop works end-to-end.
    """
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "hello from ferry-test"}),
    }
