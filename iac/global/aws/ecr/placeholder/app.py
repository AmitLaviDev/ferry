import json


def handler(event, context):
    """Placeholder handler -- replaced by real deploy in Phase 14."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "placeholder", "service": "ferry-backend"}),
    }
