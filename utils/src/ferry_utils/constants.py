"""Ferry shared constants and enums."""

from enum import StrEnum

# Dispatch payload schema versions
SCHEMA_VERSION = 1
BATCHED_SCHEMA_VERSION = 2


class ResourceType(StrEnum):
    """Supported serverless resource types."""

    LAMBDA = "lambda"
    STEP_FUNCTION = "step_function"
    API_GATEWAY = "api_gateway"


# Unified workflow filename for all dispatch types
WORKFLOW_FILENAME = "ferry.yml"
