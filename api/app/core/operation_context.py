"""Authoritative Application -> Environment policy resolution for future operations."""

from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models.base import ApplicationEnvironment


class OperationContextError(ValueError):
    """The requested environment cannot safely authorize the operation."""


_OPERATION_KINDS = {
    "database_connection_registration": ("database_connection", "registration"),
    "backup_plan": ("backup", "plan"),
    "backup_run": ("backup", "run"),
    "release_deploy": ("release", "deploy"),
}


@dataclass(frozen=True)
class ResolvedOperationContext:
    application_environment_id: str
    application_id: str
    application_identity: str
    environment_key: str
    target_type: str
    action_class: str
    policy_mode: str
    read_only: bool


def resolve_operation_context(
    db: Session, application_environment_id: str, operation_kind: str
) -> ResolvedOperationContext:
    """Resolve all policy metadata exclusively from the internal inventory."""
    if not application_environment_id:
        raise OperationContextError("application_environment_id is required")
    kind = _OPERATION_KINDS.get(operation_kind)
    if kind is None:
        raise OperationContextError("unsupported operation kind")

    environment = (
        db.query(ApplicationEnvironment)
        .options(joinedload(ApplicationEnvironment.application))
        .filter(ApplicationEnvironment.id == application_environment_id)
        .first()
    )
    if environment is None:
        raise OperationContextError("application environment not found")
    application = environment.application
    if application is None or application.id != environment.project_id:
        raise OperationContextError("application environment does not match an application")

    # Production is not overridable by the stored default or request input.
    read_only = environment.environment_key == "production" or environment.read_only_default
    if read_only:
        raise OperationContextError("production environment is enforced read-only for write-capable operations")

    target_type, action_class = kind
    return ResolvedOperationContext(
        application_environment_id=environment.id,
        application_id=application.id,
        application_identity=application.identity,
        environment_key=environment.environment_key,
        target_type=target_type,
        action_class=action_class,
        policy_mode="standard",
        read_only=False,
    )
