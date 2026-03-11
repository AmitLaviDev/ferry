"""Dispatch payload models - shared contract between Ferry App and Ferry Action.

The dispatch payload is sent via GitHub workflow_dispatch from the backend
to the action. It uses a Pydantic discriminated union for type-safe resource
validation. One dispatch per resource TYPE (not per resource).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ferry_utils.constants import BATCHED_SCHEMA_VERSION, SCHEMA_VERSION


class LambdaResource(BaseModel):
    """A Lambda function resource to build and deploy."""

    model_config = ConfigDict(frozen=True)

    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str
    function_name: str
    runtime: str


class StepFunctionResource(BaseModel):
    """A Step Functions state machine resource to deploy."""

    model_config = ConfigDict(frozen=True)

    resource_type: Literal["step_function"] = "step_function"
    name: str
    source: str
    state_machine_name: str
    definition_file: str


class ApiGatewayResource(BaseModel):
    """An API Gateway resource to deploy."""

    model_config = ConfigDict(frozen=True)

    resource_type: Literal["api_gateway"] = "api_gateway"
    name: str
    source: str
    rest_api_id: str
    stage_name: str
    spec_file: str


Resource = Annotated[
    LambdaResource | StepFunctionResource | ApiGatewayResource,
    Field(discriminator="resource_type"),
]


class DispatchPayload(BaseModel):
    """Payload sent via workflow_dispatch from Ferry App to Ferry Action.

    One payload per resource type. Contains all resources of that type
    that were affected by the push event.
    """

    model_config = ConfigDict(frozen=True)

    v: int = SCHEMA_VERSION
    resource_type: str
    resources: list[Resource]
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""


class BatchedDispatchPayload(BaseModel):
    """Batched payload sent via workflow_dispatch from Ferry App to Ferry Action.

    v2 schema: One payload per push containing ALL affected resource types,
    grouped into typed lists. Replaces per-type DispatchPayload (v1) to
    eliminate multiple workflow runs per push.
    """

    model_config = ConfigDict(frozen=True)

    v: Literal[2] = BATCHED_SCHEMA_VERSION
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resource_types(self) -> str:
        """Comma-separated list of resource types with non-empty resource lists."""
        types: list[str] = []
        if self.lambdas:
            types.append("lambda")
        if self.step_functions:
            types.append("step_function")
        if self.api_gateways:
            types.append("api_gateway")
        return ",".join(types)
