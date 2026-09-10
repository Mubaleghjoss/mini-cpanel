"""Explicit migrations for the mini cPanel internal SQLite database only."""

import argparse
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.database import Base


class MigrationError(RuntimeError):
    pass


def validate_database_path(db_path: Path, allowed_data_dir: Path) -> Path:
    data_dir = Path(allowed_data_dir).expanduser().resolve()
    candidate = Path(db_path).expanduser().resolve()
    expected = (data_dir / "minicpanel.db").resolve()
    if candidate != expected:
        raise MigrationError(f"Path is not the configured mini cPanel database: {candidate}")
    if candidate.exists() and not candidate.is_file():
        raise MigrationError(f"Database path is not a regular file: {candidate}")
    return candidate


def _baseline_up(engine) -> None:
    inventory_names = {
        "application_inventory",
        "application_environments",
        "environment_operation_contexts",
    }
    legacy_tables = [table for table in Base.metadata.sorted_tables if table.name not in inventory_names]
    Base.metadata.create_all(engine, tables=legacy_tables)


def _baseline_down(engine) -> None:
    raise MigrationError("The baseline migration cannot be removed")


def _inventory_up(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE application_inventory (
                id VARCHAR NOT NULL PRIMARY KEY,
                identity VARCHAR NOT NULL UNIQUE,
                display_name VARCHAR NOT NULL,
                source_path VARCHAR,
                classification VARCHAR NOT NULL DEFAULT 'managed_application',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT ck_application_inventory_classification CHECK (
                    classification IN ('managed_application', 'development_only', 'system_tool')
                )
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_application_inventory_identity ON application_inventory (identity)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE application_environments (
                id VARCHAR NOT NULL PRIMARY KEY,
                project_id VARCHAR NOT NULL,
                environment_key VARCHAR NOT NULL,
                runtime_path VARCHAR,
                branch VARCHAR,
                domain VARCHAR,
                service_identifier VARCHAR,
                read_only_default BOOLEAN NOT NULL DEFAULT 0,
                CONSTRAINT ck_application_environment_key CHECK (
                    environment_key IN ('production', 'staging')
                ),
                CONSTRAINT uq_application_environment_project_key UNIQUE (
                    project_id, environment_key
                ),
                FOREIGN KEY(project_id) REFERENCES application_inventory (id) ON DELETE CASCADE
            )
            """
        )


def _inventory_down(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_environments")
        connection.exec_driver_sql("DROP INDEX IF EXISTS ix_application_inventory_identity")
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_inventory")


def _operation_contexts_up(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE environment_operation_contexts (
                id VARCHAR NOT NULL PRIMARY KEY,
                application_environment_id VARCHAR NOT NULL,
                application_id VARCHAR NOT NULL,
                application_identity VARCHAR NOT NULL,
                environment_key VARCHAR NOT NULL,
                target_type VARCHAR NOT NULL,
                action_class VARCHAR NOT NULL,
                policy_mode VARCHAR NOT NULL,
                read_only BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT ck_environment_operation_context_environment_key CHECK (
                    environment_key IN ('production', 'staging')
                ),
                CONSTRAINT ck_environment_operation_context_target_type CHECK (
                    target_type IN ('database_connection', 'backup', 'release')
                ),
                CONSTRAINT ck_environment_operation_context_action_class CHECK (
                    action_class IN ('registration', 'plan', 'run', 'deploy')
                ),
                CONSTRAINT ck_environment_operation_context_policy_mode CHECK (
                    policy_mode IN ('standard', 'read_only')
                ),
                FOREIGN KEY(application_environment_id) REFERENCES application_environments (id) ON DELETE RESTRICT,
                FOREIGN KEY(application_id) REFERENCES application_inventory (id) ON DELETE RESTRICT
            )
            """
        )
        # Context fields are submission snapshots; later actions cannot rewrite them.
        connection.exec_driver_sql(
            """
            CREATE TRIGGER prevent_environment_operation_context_snapshot_updates
            BEFORE UPDATE ON environment_operation_contexts
            BEGIN
                SELECT RAISE(ABORT, 'environment operation context snapshots are immutable');
            END
            """
        )


def _operation_contexts_down(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS prevent_environment_operation_context_snapshot_updates")
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS validate_environment_operation_context_application")
        connection.exec_driver_sql("DROP TABLE IF EXISTS environment_operation_contexts")


def _operation_context_safety_up(engine) -> None:
    """Rebuild the Phase 2.1 table with complete integrity gates, preserving snapshots."""
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS prevent_environment_operation_context_snapshot_updates")
        connection.exec_driver_sql(
            """
            CREATE TABLE environment_operation_contexts_rebuilt (
                id VARCHAR NOT NULL PRIMARY KEY, application_environment_id VARCHAR NOT NULL,
                application_id VARCHAR NOT NULL, application_identity VARCHAR NOT NULL,
                environment_key VARCHAR NOT NULL, target_type VARCHAR NOT NULL,
                action_class VARCHAR NOT NULL, policy_mode VARCHAR NOT NULL,
                read_only BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
                CONSTRAINT ck_environment_operation_context_environment_key CHECK (environment_key IN ('production', 'staging')),
                CONSTRAINT ck_environment_operation_context_target_type CHECK (target_type IN ('database_connection', 'backup', 'release')),
                CONSTRAINT ck_environment_operation_context_action_class CHECK (action_class IN ('registration', 'plan', 'run', 'deploy')),
                CONSTRAINT ck_environment_operation_context_policy_mode CHECK (policy_mode IN ('standard', 'read_only')),
                CONSTRAINT ck_environment_operation_context_read_only CHECK (read_only IN (0, 1)),
                FOREIGN KEY(application_environment_id) REFERENCES application_environments (id) ON DELETE RESTRICT,
                FOREIGN KEY(application_id) REFERENCES application_inventory (id) ON DELETE RESTRICT
            )
            """
        )
        connection.exec_driver_sql("INSERT INTO environment_operation_contexts_rebuilt SELECT * FROM environment_operation_contexts")
        connection.exec_driver_sql("DROP TABLE environment_operation_contexts")
        connection.exec_driver_sql("ALTER TABLE environment_operation_contexts_rebuilt RENAME TO environment_operation_contexts")
        connection.exec_driver_sql(
            """
            CREATE TRIGGER validate_environment_operation_context_application
            BEFORE INSERT ON environment_operation_contexts
            WHEN NOT EXISTS (SELECT 1 FROM application_environments
                             WHERE id = NEW.application_environment_id AND project_id = NEW.application_id)
            BEGIN
                SELECT RAISE(ABORT, 'operation context application does not match environment');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER prevent_environment_operation_context_snapshot_updates
            BEFORE UPDATE ON environment_operation_contexts
            BEGIN
                SELECT RAISE(ABORT, 'environment operation context snapshots are immutable');
            END
            """
        )


def _operation_context_safety_down(engine) -> None:
    """Reverse the safety-table rebuild while preserving its snapshots."""
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS prevent_environment_operation_context_snapshot_updates")
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS validate_environment_operation_context_application")
        connection.exec_driver_sql("ALTER TABLE environment_operation_contexts RENAME TO environment_operation_contexts_rebuilt")
        connection.exec_driver_sql(
            """
            CREATE TABLE environment_operation_contexts (
                id VARCHAR NOT NULL PRIMARY KEY, application_environment_id VARCHAR NOT NULL,
                application_id VARCHAR NOT NULL, application_identity VARCHAR NOT NULL,
                environment_key VARCHAR NOT NULL, target_type VARCHAR NOT NULL,
                action_class VARCHAR NOT NULL, policy_mode VARCHAR NOT NULL,
                read_only BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
                CONSTRAINT ck_environment_operation_context_environment_key CHECK (environment_key IN ('production', 'staging')),
                CONSTRAINT ck_environment_operation_context_target_type CHECK (target_type IN ('database_connection', 'backup', 'release')),
                CONSTRAINT ck_environment_operation_context_action_class CHECK (action_class IN ('registration', 'plan', 'run', 'deploy')),
                CONSTRAINT ck_environment_operation_context_policy_mode CHECK (policy_mode IN ('standard', 'read_only')),
                FOREIGN KEY(application_environment_id) REFERENCES application_environments (id) ON DELETE RESTRICT,
                FOREIGN KEY(application_id) REFERENCES application_inventory (id) ON DELETE RESTRICT
            )
            """
        )
        connection.exec_driver_sql("INSERT INTO environment_operation_contexts SELECT * FROM environment_operation_contexts_rebuilt")
        connection.exec_driver_sql("DROP TABLE environment_operation_contexts_rebuilt")
        connection.exec_driver_sql(
            """
            CREATE TRIGGER prevent_environment_operation_context_snapshot_updates
            BEFORE UPDATE ON environment_operation_contexts
            BEGIN
                SELECT RAISE(ABORT, 'environment operation context snapshots are immutable');
            END
            """
        )


MIGRATIONS: tuple[tuple[int, str, Callable, Callable], ...] = (
    (1, "baseline", _baseline_up, _baseline_down),
    (2, "phase_1_inventory", _inventory_up, _inventory_down),
    (3, "phase_2_1_operation_contexts", _operation_contexts_up, _operation_contexts_down),
    (4, "phase_2_1_operation_context_safety", _operation_context_safety_up, _operation_context_safety_down),
)


def _engine_for(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def _prepare(db_path: Path, allowed_data_dir: Path):
    validated = validate_database_path(db_path, allowed_data_dir)
    validated.parent.mkdir(parents=True, exist_ok=True)
    engine = _engine_for(validated)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    return validated, engine


def schema_version(db_path: Path, allowed_data_dir: Path) -> int:
    validated = validate_database_path(db_path, allowed_data_dir)
    if not validated.exists():
        return 0
    engine = _engine_for(validated)
    try:
        with engine.connect() as connection:
            exists = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).first()
            if not exists:
                return 0
            return int(connection.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one())
    finally:
        engine.dispose()


def migrate(action: str, db_path: Path, allowed_data_dir: Path) -> int:
    if action not in {"up", "down", "rollback"}:
        raise MigrationError(f"Unsupported migration action: {action}")
    _, engine = _prepare(db_path, allowed_data_dir)
    try:
        with engine.connect() as connection:
            applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}

        if action == "up":
            for version, name, up, _ in MIGRATIONS:
                if version not in applied:
                    up(engine)
                    with engine.begin() as connection:
                        connection.execute(
                            text("INSERT INTO schema_migrations(version, name) VALUES (:version, :name)"),
                            {"version": version, "name": name},
                        )
        else:
            current = max(applied, default=0)
            if current <= 1:
                raise MigrationError("No reversible migration is applied")
            version, _, _, down = next(item for item in MIGRATIONS if item[0] == current)
            down(engine)
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM schema_migrations WHERE version = :version"), {"version": version})
        return schema_version(db_path, allowed_data_dir)
    finally:
        engine.dispose()


def configured_paths() -> tuple[Path, Path]:
    data_dir = settings.CPANEL_DATA_DIR
    return data_dir / "minicpanel.db", data_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "down", "rollback", "version"))
    args = parser.parse_args()
    db_path, data_dir = configured_paths()
    version = schema_version(db_path, data_dir) if args.action == "version" else migrate(args.action, db_path, data_dir)
    print(f"mini cPanel internal schema version: {version}")


if __name__ == "__main__":
    main()
