import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.applications import list_applications, mutation_user, read_user
from app.core.inventory_seed import seed_inventory
from app.core.migrations import MigrationError, migrate, schema_version, validate_database_path
from app.models.base import ApplicationEnvironment, ApplicationInventory, Base, User
from app.schemas.applications import ApplicationResponse


class InventoryPhase1Tests(unittest.TestCase):
    def make_session(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        return sessionmaker(bind=engine)()

    def test_migration_up_down_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            db_path = data_dir / "minicpanel.db"
            migrate("up", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, allowed_data_dir=data_dir), 4)
            with sqlite3.connect(db_path) as connection:
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='application_inventory'"
                ).fetchone()
                self.assertIsNotNone(table)

            migrate("down", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, allowed_data_dir=data_dir), 3)
            migrate("down", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, allowed_data_dir=data_dir), 2)
            migrate("down", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, allowed_data_dir=data_dir), 1)
            with sqlite3.connect(db_path) as connection:
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='application_inventory'"
                ).fetchone()
                self.assertIsNone(table)

            migrate("up", db_path=db_path, allowed_data_dir=data_dir)
            migrate("rollback", db_path=db_path, allowed_data_dir=data_dir)
            self.assertEqual(schema_version(db_path, allowed_data_dir=data_dir), 3)

    def test_migration_rejects_arbitrary_database_path(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaisesRegex(MigrationError, "configured mini cPanel database"):
                validate_database_path(data_dir / "other.db", data_dir)

    def test_import_does_not_apply_schema_migrations(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["MINICPANEL_DATA_DIR"] = directory
            result = subprocess.run(
                [sys.executable, "-c", "import app.main"],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stderr, "")
            db_path = Path(directory) / "minicpanel.db"
            if db_path.exists():
                with sqlite3.connect(db_path) as connection:
                    tables = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                self.assertEqual(tables, [])

    def test_environment_defaults_and_unique_key(self):
        db = self.make_session()
        app = ApplicationInventory(identity="defaults", display_name="Defaults")
        production = ApplicationEnvironment(environment_key="production")
        staging = ApplicationEnvironment(environment_key="staging")
        app.environments.extend([production, staging])
        db.add(app)
        db.commit()

        self.assertIs(production.read_only_default, True)
        self.assertIs(staging.read_only_default, False)

        db.add(ApplicationEnvironment(project_id=app.id, environment_key="staging"))
        with self.assertRaises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(ApplicationInventory(identity="defaults", display_name="Duplicate"))
        with self.assertRaises(IntegrityError):
            db.commit()

    def test_inventory_response_excludes_credentials(self):
        db = self.make_session()
        item = ApplicationInventory(identity="safe", display_name="Safe application")
        item.environments.append(
            ApplicationEnvironment(
                environment_key="production",
                runtime_path="/srv/safe",
                domain="safe.example",
                branch="main",
                service_identifier="safe.service",
            )
        )
        db.add(item)
        db.commit()

        body = [ApplicationResponse.model_validate(row).model_dump(mode="json") for row in list_applications(db=db)]
        serialized = json.dumps(body).lower()
        for forbidden in ("password", "credential", "database", "secret", "token"):
            self.assertNotIn(forbidden, serialized)

    def test_inventory_rbac(self):
        for role in ("super_admin", "developer", "viewer"):
            user = User(username=role, password_hash="unused", role=role)
            self.assertIs(read_user(current_user=user), user)

        admin = User(username="admin", password_hash="unused", role="super_admin")
        self.assertIs(mutation_user(current_user=admin), admin)
        for role in ("developer", "viewer"):
            user = User(username=role, password_hash="unused", role=role)
            with self.assertRaises(HTTPException) as raised:
                mutation_user(current_user=user)
            self.assertEqual(raised.exception.status_code, 403)

    def test_seed_reconciles_existing_sma_metadata_only(self):
        db = self.make_session()
        sma = ApplicationInventory(identity="sma-afbs", display_name="SMA AFBS")
        sma.environments.append(ApplicationEnvironment(environment_key="production", branch="main"))
        keuangan = ApplicationInventory(identity="keuangan-sma-afbs", display_name="Keuangan SMA AFBS")
        db.add_all([sma, keuangan])
        db.commit()

        self.assertEqual(seed_inventory(db), 2)
        db.refresh(sma)
        db.refresh(keuangan)
        self.assertEqual(sma.source_path, "/home/hermesadmin/projects/akses-smaafbs")
        self.assertEqual({item.environment_key for item in sma.environments}, {"staging"})
        staging = sma.environments[0]
        self.assertEqual(staging.runtime_path, "/var/www/app-smaafbs-staging/public")
        self.assertEqual(staging.domain, "staging-app.smaafbs.sch.id")
        self.assertIsNone(staging.branch)
        self.assertIsNone(staging.service_identifier)
        self.assertIs(staging.read_only_default, False)
        self.assertEqual(keuangan.source_path, "/home/hermesadmin/projects/keuangan-smaafbs")
        self.assertEqual(keuangan.environments, [])

    def test_initial_inventory_seed_is_idempotent(self):
        db = self.make_session()
        self.assertEqual(seed_inventory(db), 4)
        self.assertEqual(seed_inventory(db), 0)
        self.assertEqual(db.query(ApplicationInventory).count(), 4)

        pkg = db.query(ApplicationInventory).filter_by(identity="pkgenerus").one()
        self.assertEqual(pkg.source_path, "/home/hermesadmin/projects/pembinaan-karakter-generus")
        environments = {item.environment_key: item for item in pkg.environments}
        self.assertEqual(set(environments), {"production", "staging"})
        self.assertEqual(environments["production"].runtime_path, "/var/www/pkgenerus.my.id")
        self.assertEqual(environments["production"].domain, "pkgenerus.my.id")
        self.assertEqual(environments["production"].branch, "main")
        self.assertIs(environments["production"].read_only_default, True)
        self.assertEqual(environments["staging"].runtime_path, "/var/www/pkgenerus-staging")
        self.assertEqual(environments["staging"].domain, "staging.pkgenerus.my.id")
        self.assertEqual(environments["staging"].branch, "develop")
        self.assertIs(environments["staging"].read_only_default, False)

        sma = db.query(ApplicationInventory).filter_by(identity="sma-afbs").one()
        self.assertEqual(sma.source_path, "/home/hermesadmin/projects/akses-smaafbs")
        staging = {item.environment_key: item for item in sma.environments}
        self.assertEqual(set(staging), {"staging"})
        self.assertEqual(staging["staging"].runtime_path, "/var/www/app-smaafbs-staging/public")
        self.assertEqual(staging["staging"].domain, "staging-app.smaafbs.sch.id")
        self.assertIsNone(staging["staging"].branch)
        self.assertIsNone(staging["staging"].service_identifier)
        self.assertIs(staging["staging"].read_only_default, False)

        keuangan = db.query(ApplicationInventory).filter_by(identity="keuangan-sma-afbs").one()
        self.assertEqual(keuangan.source_path, "/home/hermesadmin/projects/keuangan-smaafbs")
        self.assertEqual(keuangan.environments, [])
        self.assertEqual(db.query(ApplicationInventory).filter_by(identity="mini-cpanel").one().environments, [])


if __name__ == "__main__":
    unittest.main()
