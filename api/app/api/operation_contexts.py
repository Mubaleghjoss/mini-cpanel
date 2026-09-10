from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import RoleChecker
from app.core.database import get_db
from app.core.operation_context import OperationContextError, resolve_operation_context
from app.models.base import User
from app.schemas.operation_contexts import (
    OperationContextDryRunRequest,
    OperationContextDryRunResponse,
)

router = APIRouter()
_super_admin = RoleChecker(["super_admin"])


def validation_user(current_user: User = Depends(_super_admin)) -> User:
    return _super_admin(current_user)


@router.post("/validate-dry-run", response_model=OperationContextDryRunResponse)
def validate_dry_run(
    payload: OperationContextDryRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(validation_user),
):
    """Validate a future operation context without creating a request or resource."""
    try:
        resolved = resolve_operation_context(
            db, payload.application_environment_id, payload.operation_kind
        )
        return OperationContextDryRunResponse(**resolved.__dict__)
    except OperationContextError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
