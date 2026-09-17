"""
Unit and Integration Tests for Auth & Admin Panel Module
"""

import unittest
from app.database import init_db
from app.auth import (
    init_auth_tables,
    authenticate_user,
    validate_token,
    logout_user,
    change_password,
    get_admin_stats,
    get_all_tasks,
    update_task_status,
    DEFAULT_ADMIN_USER,
    DEFAULT_ADMIN_PASS
)

class TestAuthAndAdmin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        init_auth_tables()

    def test_01_admin_login_success(self):
        res = authenticate_user(DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASS)
        self.assertIsNotNone(res)
        self.assertIn("token", res)
        self.assertEqual(res["user"]["username"], DEFAULT_ADMIN_USER)
        self.assertEqual(res["user"]["role"], "admin")

    def test_02_admin_login_wrong_credentials(self):
        res = authenticate_user(DEFAULT_ADMIN_USER, "wrong_password_123")
        self.assertIsNone(res)
        res2 = authenticate_user("nonexistent_user", "password")
        self.assertIsNone(res2)

    def test_03_validate_token(self):
        login_res = authenticate_user(DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASS)
        token = login_res["token"]
        user = validate_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], DEFAULT_ADMIN_USER)

        invalid_user = validate_token("invalid_dummy_token_hex")
        self.assertIsNone(invalid_user)

    def test_04_admin_stats(self):
        stats = get_admin_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("total_lots", stats)
        self.assertGreater(stats["total_lots"], 1000)
        self.assertIn("total_companies", stats)
        self.assertGreater(stats["total_companies"], 300)
        self.assertIn("total_contract_sum", stats)
        self.assertGreater(stats["total_contract_sum"], 1000000000)
        self.assertIn("platform_counts", stats)

    def test_05_admin_tasks_and_status_update(self):
        tasks = get_all_tasks()
        self.assertIsInstance(tasks, list)
        if len(tasks) > 0:
            task_id = tasks[0]["id"]
            ok = update_task_status(task_id, "JARAYONDA")
            self.assertTrue(ok)
            updated_tasks = get_all_tasks()
            found = next(t for t in updated_tasks if t["id"] == task_id)
            self.assertEqual(found["status"], "JARAYONDA")

    def test_06_change_password_and_logout(self):
        ok, msg = change_password(DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASS, "temp_new_pass_2026")
        self.assertTrue(ok)

        res = authenticate_user(DEFAULT_ADMIN_USER, "temp_new_pass_2026")
        self.assertIsNotNone(res)
        token = res["token"]

        ok_revert, _ = change_password(DEFAULT_ADMIN_USER, "temp_new_pass_2026", DEFAULT_ADMIN_PASS)
        self.assertTrue(ok_revert)

        logged_out = logout_user(token)
        self.assertTrue(logged_out)
        self.assertIsNone(validate_token(token))

if __name__ == "__main__":
    unittest.main()
