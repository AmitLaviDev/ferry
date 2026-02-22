"""Ferry shared constants and enums."""

from enum import StrEnum

# Dispatch payload schema version
SCHEMA_VERSION = 1


class ResourceType(StrEnum):
    """Supported serverless resource types."""

    LAMBDA = "lambda"
    STEP_FUNCTION = "step_function"
    API_GATEWAY = "api_gateway"


# Maps ResourceType to workflow dispatch type names
RESOURCE_TYPE_WORKFLOW_MAP: dict[ResourceType, str] = {
    ResourceType.LAMBDA: "lambdas",
    ResourceType.STEP_FUNCTION: "step_functions",
    ResourceType.API_GATEWAY: "api_gateways",
}
