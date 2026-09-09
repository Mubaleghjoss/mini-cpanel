from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import RoleChecker
from app.core.database import get_db
from app.models.base import ApplicationEnvironment, ApplicationInventory, User
from app.schemas.applications import ApplicationCreate, ApplicationResponse, ApplicationUpdate


router = APIRouter()
read_user = RoleChecker(["super_admin", "developer", "viewer"])
_super_admin = RoleChecker(["super_admin"])


def mutation_user(current_user: User = Depends(_super_admin)) -> User:
    return _super_admin(current_user)


def _query(db: Session):
    return db.query(ApplicationInventory).options(selectinload(ApplicationInventory.environments))


def _get_or_404(db: Session, application_id: str) -> ApplicationInventory:
    item = _query(db).filter(ApplicationInventory.id == application_id).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return item


def _environment(payload) -> ApplicationEnvironment:
    return ApplicationEnvironment(**payload.model_dump())


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(read_user),
):
    return _query(db).order_by(ApplicationInventory.display_name).all()


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_user),
):
    return _get_or_404(db, application_id)


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(mutation_user),
):
    item = ApplicationInventory(
        identity=payload.identity,
        display_name=payload.display_name,
        source_path=payload.source_path,
        classification=payload.classification,
        environments=[_environment(value) for value in payload.environments],
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Application identity already exists") from exc
    return _get_or_404(db, item.id)


@router.put("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: str,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(mutation_user),
):
    item = _get_or_404(db, application_id)
    values = payload.model_dump(exclude_unset=True, exclude={"environments"})
    for key, value in values.items():
        setattr(item, key, value)
    if payload.environments is not None:
        item.environments = [_environment(value) for value in payload.environments]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Environment key already exists") from exc
    return _get_or_404(db, application_id)
