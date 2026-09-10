import asyncio
import json
import unittest
from unittest.mock import Mock, patch

from fastapi import status

from app.api.dependencies import get_current_user
from app.main import app
from app.models.base import User


class DatabaseQueryDeprecationTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def post_raw_query(self):
        async def request():
            body = json.dumps({"query": "SELECT 1"}).encode()
            response_events = []

            request_received = False
            response_complete = asyncio.Event()

            async def receive():
                nonlocal request_received
                if not request_received:
                    request_received = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await response_complete.wait()
                return {"type": "http.disconnect"}

            async def send(event):
                response_events.append(event)
                if event["type"] == "http.response.body" and not event.get("more_body", False):
                    response_complete.set()

            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/databases/primary-sqlite/query",
                    "raw_path": b"/api/v1/databases/primary-sqlite/query",
                    "query_string": b"",
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                    "client": ("testclient", 50000),
                    "server": ("testserver", 80),
                },
                receive,
                send,
            )
            return next(event for event in response_events if event["type"] == "http.response.start")

        return asyncio.run(request())

    def test_mounted_raw_query_route_is_unique_and_unavailable_without_authentication(self):
        query_routes = [
            (path, operations)
            for path, operations in app.openapi()["paths"].items()
            if path.startswith("/api/v1/databases/") and "query" in path
        ]
        self.assertEqual(len(query_routes), 1)
        self.assertEqual(query_routes[0][0], "/api/v1/databases/{id}/query")
        self.assertEqual(set(query_routes[0][1]), {"post"})

        authenticate = Mock()
        app.dependency_overrides[get_current_user] = authenticate
        with patch("app.api.databases.get_dynamic_engine") as get_dynamic_engine:
            response = self.post_raw_query()

        self.assertEqual(response["status"], status.HTTP_410_GONE)
        authenticate.assert_not_called()
        get_dynamic_engine.assert_not_called()

    def test_mounted_raw_query_route_short_circuits_non_admin_and_super_admin(self):
        for role in ("viewer", "super_admin"):
            with self.subTest(role=role):
                authenticate = Mock(return_value=User(
                    username=role, password_hash="unused", role=role
                ))
                app.dependency_overrides[get_current_user] = authenticate
                with patch("app.api.databases.get_dynamic_engine") as get_dynamic_engine:
                    response = self.post_raw_query()

                self.assertEqual(response["status"], status.HTTP_410_GONE)
                authenticate.assert_not_called()
                get_dynamic_engine.assert_not_called()
                app.dependency_overrides.clear()



if __name__ == "__main__":
    unittest.main()
