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
        "source_path": "/home/hermesadmin/projects/akses-smaafbs",
        "classification": "managed_application",
        "environments": (
            {
                "environment_key": "staging",
                "runtime_path": "/var/www/app-smaafbs-staging/public",
                "domain": "staging-app.smaafbs.sch.id",
                "branch": None,
                "service_identifier": None,
                "read_only_default": False,
            },
        ),
    },
    {
        "identity": "keuangan-sma-afbs",
        "display_name": "Keuangan SMA AFBS",
        "source_path": "/home/hermesadmin/projects/keuangan-smaafbs",
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


def _reconcile_environments(item: ApplicationInventory, environments: tuple[dict, ...]) -> None:
    desired = {environment["environment_key"]: environment for environment in environments}
    for environment in list(item.environments):
        if environment.environment_key not in desired:
            item.environments.remove(environment)
    current = {environment.environment_key: environment for environment in item.environments}
    for key, values in desired.items():
        environment = current.get(key)
        if environment is None:
            item.environments.append(ApplicationEnvironment(**values))
            continue
        for field, value in values.items():
            setattr(environment, field, value)


def seed_inventory(db: Session) -> int:
    created = 0
    reconciled_identities = {"sma-afbs", "keuangan-sma-afbs"}
    for record in INITIAL_INVENTORY:
        item = db.query(ApplicationInventory).filter_by(identity=record["identity"]).first()
        if item is not None:
            if record["identity"] in reconciled_identities:
                for field in ("display_name", "source_path", "classification"):
                    setattr(item, field, record[field])
                _reconcile_environments(item, record["environments"])
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
