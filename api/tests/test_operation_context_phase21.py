import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.operation_contexts import validate_dry_run, validation_user
from app.core.migrations import migrate, schema_version
from app.core.operation_context import OperationContextError, resolve_operation_context
from app.models.base import (
    ApplicationEnvironment,
    ApplicationInventory,
    Base,
    EnvironmentOperationContext,
    User,
)
from app.schemas.operation_contexts import OperationContextDryRunRequest


class OperationContextPhase21Tests(unittest.TestCase):
    def make_session(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        return sessionmaker(bind=engine)()

    def environment(self, db, key="staging"):
        application = ApplicationInventory(identity="safe-app", display_name="Safe App")
        environment = ApplicationEnvironment(environment_key=key)
        application.environments.append(environment)
        db.add(application)
        db.commit()
        return application, environment

    def test_resolver_uses_environment_as_the_only_authoritative_input(self):
        db = self.make_session()
        application, environment = self.environment(db)

        resolved = resolve_operation_context(db, environment.id, "backup_plan")

        self.assertEqual(resolved.application_id, application.id)
        self.assertEqual(resolved.application_identity, "safe-app")
        self.assertEqual(resolved.application_environment_id, environment.id)
        self.assertEqual(resolved.environment_key, "staging")
        self.assertEqual(resolved.target_type, "backup")
        self.assertEqual(resolved.action_class, "plan")
        self.assertEqual(resolved.policy_mode, "standard")
        self.assertFalse(resolved.read_only)

    def test_resolver_rejects_absent_unknown_deleted_or_mismatched_context(self):
        db = self.make_session()
        application, environment = self.environment(db)
        with self.assertRaisesRegex(OperationContextError, "environment_id is required"):
            resolve_operation_context(db, "", "backup_plan")
        with self.assertRaisesRegex(OperationContextError, "not found"):
            resolve_operation_context(db, "missing", "backup_plan")
        environment.project_id = "missing-application"
        with self.assertRaisesRegex(OperationContextError, "does not match"):
            resolve_operation_context(db, environment.id, "backup_plan")
        db.rollback()
        db.delete(environment)
        db.commit()
        with self.assertRaisesRegex(OperationContextError, "not found"):
            resolve_operation_context(db, environment.id, "backup_plan")
        self.assertEqual(application.identity, "safe-app")

    def test_production_write_capable_operations_are_server_side_denied(self):
        db = self.make_session()
        _, environment = self.environment(db, key="production")
        for kind in ("database_connection_registration", "backup_plan", "backup_run", "release_deploy"):
            with self.assertRaisesRegex(OperationContextError, "production.*read-only"):
                resolve_operation_context(db, environment.id, kind)

    def test_dry_run_requires_super_admin_and_has_no_secret_or_persistence(self):
        db = self.make_session()
        _, environment = self.environment(db)
        request = OperationContextDryRunRequest(
            application_environment_id=environment.id,
            operation_kind="database_connection_registration",
        )
        admin = User(username="admin", password_hash="unused", role="super_admin")

        response = validate_dry_run(payload=request, db=db, current_user=admin)
        body = response.model_dump(mode="json")
        self.assertEqual(body["application_environment_id"], environment.id)
        serialized = json.dumps(body).lower()
        for forbidden in ("password", "credential", "secret", "token", "host", "username"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(db.query(ApplicationInventory).count(), 1)
        self.assertEqual(db.query(ApplicationEnvironment).count(), 1)
        self.assertEqual(db.query(EnvironmentOperationContext).count(), 0)

        developer = User(username="dev", password_hash="unused", role="developer")
        with self.assertRaises(HTTPException) as raised:
            validation_user(current_user=developer)
        self.assertEqual(raised.exception.status_code, 403)

    def test_context_migration_is_reversible_and_preserves_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            db_path = data_dir / "minicpanel.db"
            migrate("up", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, data_dir), 4)
            with sqlite3.connect(db_path) as connection:
                self.assertIsNotNone(connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='environment_operation_contexts'"
                ).fetchone())
                self.assertIsNotNone(connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name='prevent_environment_operation_context_snapshot_updates'"
                ).fetchone())
                self.assertIsNotNone(connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name='validate_environment_operation_context_application'"
                ).fetchone())
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    "INSERT INTO application_inventory "
                    "(id, identity, display_name, classification, created_at, updated_at) "
                    "VALUES ('existing', 'existing-app', 'Existing App', 'managed_application', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
                connection.execute(
                    "INSERT INTO application_environments (id, project_id, environment_key, read_only_default) "
                    "VALUES ('existing-staging', 'existing', 'staging', 0)"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO environment_operation_contexts "
                        "(id, application_environment_id, application_id, application_identity, environment_key, "
                        "target_type, action_class, policy_mode, read_only, created_at) "
                        "VALUES ('bad-fk', 'missing', 'existing', 'existing-app', 'staging', "
                        "'backup', 'plan', 'standard', 0, CURRENT_TIMESTAMP)"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO environment_operation_contexts "
                        "(id, application_environment_id, application_id, application_identity, environment_key, "
                        "target_type, action_class, policy_mode, read_only, created_at) "
                        "VALUES ('bad-pair', 'existing-staging', 'other', 'existing-app', 'staging', "
                        "'backup', 'plan', 'standard', 0, CURRENT_TIMESTAMP)"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO environment_operation_contexts "
                        "(id, application_environment_id, application_id, application_identity, environment_key, "
                        "target_type, action_class, policy_mode, read_only, created_at) "
                        "VALUES ('bad-check', 'existing-staging', 'existing', 'existing-app', 'staging', "
                        "'backup', 'plan', 'standard', 2, CURRENT_TIMESTAMP)"
                    )
                connection.execute(
                    "INSERT INTO environment_operation_contexts "
                    "(id, application_environment_id, application_id, application_identity, environment_key, "
                    "target_type, action_class, policy_mode, read_only, created_at) "
                    "VALUES ('immutable', 'existing-staging', 'existing', 'existing-app', 'staging', "
                    "'backup', 'plan', 'standard', 0, CURRENT_TIMESTAMP)"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE environment_operation_contexts SET target_type = 'release' WHERE id = 'immutable'"
                    )
                connection.commit()

            migrate("down", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, data_dir), 3)
            migrate("down", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, data_dir), 2)
            with sqlite3.connect(db_path) as connection:
                self.assertIsNone(connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='environment_operation_contexts'"
                ).fetchone())
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM application_inventory").fetchone()[0], 1)
