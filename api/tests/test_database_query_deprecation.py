import unittest
from unittest.mock import patch

from fastapi import HTTPException, status

from app.api.databases import disabled_query_router, run_disabled_database_query
from app.api.dependencies import RoleChecker
from app.models.base import User


class DatabaseQueryDeprecationTests(unittest.TestCase):
    def test_raw_sql_query_is_gone_for_unauthenticated_and_super_admin_requests(self):
        super_admin = User(username="admin", password_hash="unused", role="super_admin")
        self.assertIs(RoleChecker(["super_admin"])(current_user=super_admin), super_admin)
        route = disabled_query_router.routes[0]
        self.assertEqual(route.path, "/{id}/query")
        self.assertEqual(route.dependencies, [])

        with (
            patch("app.core.database_admin.get_dynamic_engine") as get_dynamic_engine,
            self.assertRaises(HTTPException) as raised,
        ):
            run_disabled_database_query(id="primary-sqlite")

        self.assertEqual(raised.exception.status_code, status.HTTP_410_GONE)
        self.assertEqual(raised.exception.detail, "Raw SQL queries are no longer available.")
        get_dynamic_engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
