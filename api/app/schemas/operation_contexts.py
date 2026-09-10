from typing import Literal

from pydantic import BaseModel, ConfigDict


OperationKind = Literal[
    "database_connection_registration",
    "backup_plan",
    "backup_run",
    "release_deploy",
]


class OperationContextDryRunRequest(BaseModel):
    """Only an environment and operation kind may be supplied by a caller."""

    model_config = ConfigDict(extra="forbid")

    application_environment_id: str
    operation_kind: OperationKind


class OperationContextDryRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_environment_id: str
    application_id: str
    application_identity: str
    environment_key: str
    target_type: str
    action_class: str
    policy_mode: Literal["standard"]
    read_only: bool
