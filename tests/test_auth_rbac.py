from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from digital_brain.service import DigitalBrainService


class AuthRbacServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_env = os.environ.copy()
        os.environ["DIGITAL_BRAIN_AUTH_ENABLED"] = "1"
        os.environ["DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER"] = "admin"
        os.environ["DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD"] = "admin123"

        self._tmp = TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "brain.db"
        self.service = DigitalBrainService(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_bootstrap_admin_login_and_logout(self) -> None:
        login = self.service.login(username="admin", password="admin123")
        self.assertIn("session_token", login)
        self.assertEqual(((login.get("user") or {}).get("role")), "admin")
        token = str(login.get("session_token") or "")
        current = self.service.get_authenticated_user(token, refresh=False)
        self.assertIsNotNone(current)
        self.assertEqual(((current or {}).get("role")), "admin")

        self.service.logout(token)
        after_logout = self.service.get_authenticated_user(token, refresh=False)
        self.assertIsNone(after_logout)

    def test_invalid_credentials_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.login(username="admin", password="wrong")

    def test_operator_user_and_session_expiry(self) -> None:
        user = self.service.create_user(
            username="operator1",
            password="operator123",
            role="operator",
            upsert=True,
        )
        self.assertEqual(user.get("role"), "operator")

        login = self.service.login(username="operator1", password="operator123")
        token = str(login.get("session_token") or "")
        current = self.service.get_authenticated_user(token, refresh=False)
        self.assertIsNotNone(current)
        self.assertEqual(((current or {}).get("role")), "operator")

        session_id = str((current or {}).get("session_id") or "")
        self.assertTrue(session_id)
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        self.service.repo.touch_auth_session(session_id=session_id, expires_at=expired)
        expired_user = self.service.get_authenticated_user(token, refresh=False)
        self.assertIsNone(expired_user)

    def test_auth_disabled_rejects_login_endpoint(self) -> None:
        os.environ["DIGITAL_BRAIN_AUTH_ENABLED"] = "0"
        service = DigitalBrainService(self.db_path)
        self.assertFalse(service.auth_enabled)
        with self.assertRaises(ValueError):
            service.login(username="admin", password="admin123")

    def test_admin_user_management(self) -> None:
        created = self.service.create_user(
            username="operator2",
            password="operator234",
            role="operator",
            upsert=True,
        )
        self.assertEqual(created.get("role"), "operator")

        users = self.service.list_users()
        self.assertTrue(any(row.get("username") == "operator2" for row in users))

        updated = self.service.update_user(
            user_id=int(created.get("id") or 0),
            role="admin",
            is_active=True,
            password="new-secret",
        )
        self.assertEqual(updated.get("role"), "admin")
        login = self.service.login(username="operator2", password="new-secret")
        self.assertIn("session_token", login)

    def test_cannot_deactivate_last_admin(self) -> None:
        users = self.service.list_users()
        admin = next((row for row in users if row.get("username") == "admin"), None)
        self.assertIsNotNone(admin)
        with self.assertRaises(ValueError):
            self.service.update_user(
                user_id=int((admin or {}).get("id") or 0),
                is_active=False,
            )


if __name__ == "__main__":
    unittest.main()
