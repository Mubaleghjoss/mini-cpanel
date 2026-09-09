"""Idempotent Phase 1 inventory initialization command."""

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.migrations import configured_paths, schema_version, validate_database_path
from app.models.base import ApplicationEnvironment, ApplicationInventory


INITIAL_INVENTORY = (
    {
        "identity": "pkgenerus",
        "display_name": "PKGenerus",
        "source_path": "/home/hermesadmin/projects/pembinaan-karakter-generus",
        "classification": "managed_application",
        "environments": (
            {
                "environment_key": "production",
                "runtime_path": "/var/www/pkgenerus.my.id",
                "domain": "pkgenerus.my.id",
                "branch": "main",
                "read_only_default": True,
            },
            {
                "environment_key": "staging",
                "runtime_path": "/var/www/pkgenerus-staging",
                "domain": "staging.pkgenerus.my.id",
                "branch": "develop",
                "read_only_default": False,
            },
        ),
    },
    {
        "identity": "sma-afbs",
        "display_name": "SMA AFBS",
        "classification": "managed_application",
        "environments": (),
    },
    {
        "identity": "keuangan-sma-afbs",
        "display_name": "Keuangan SMA AFBS",
        "classification": "development_only",
        "environments": (),
    },
    {
        "identity": "mini-cpanel",
        "display_name": "Mini cPanel",
        "classification": "system_tool",
        "environments": (),
    },
)


def seed_inventory(db: Session) -> int:
    created = 0
    for record in INITIAL_INVENTORY:
        if db.query(ApplicationInventory).filter_by(identity=record["identity"]).first() is not None:
            continue
        values = {key: value for key, value in record.items() if key != "environments"}
        item = ApplicationInventory(**values)
        item.environments = [ApplicationEnvironment(**value) for value in record["environments"]]
        db.add(item)
        created += 1
    db.commit()
    return created


def main() -> None:
    db_path, data_dir = configured_paths()
    validate_database_path(db_path, data_dir)
    if schema_version(db_path, data_dir) < 2:
        raise SystemExit("Phase 1 migration is not applied; run migrations up first")
    db = SessionLocal()
    try:
        created = seed_inventory(db)
    finally:
        db.close()
    print(f"Phase 1 inventory initialized; created {created} record(s)")


if __name__ == "__main__":
    main()
