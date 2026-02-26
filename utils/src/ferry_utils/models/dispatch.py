"""Dispatch payload models - shared contract between Ferry App and Ferry Action.

The dispatch payload is sent via GitHub workflow_dispatch from the backend
to the action. It uses a Pydantic discriminated union for type-safe resource
validation. One dispatch per resource TYPE (not per resource).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ferry_utils.constants import SCHEMA_VERSION


class LambdaResource(BaseModel):
    """A Lambda function resource to build and deploy."""

    model_config = ConfigDict(frozen=True)

    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str


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
