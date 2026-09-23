from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import admin


class _FakeQuery:
    def __init__(self, users):
        self.users = users

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.users


class _FakeDb:
    def __init__(self, users):
        self.users = users
        self.deleted = []
        self.committed = False
        self.rolled_back = False

    def query(self, _model):
        return _FakeQuery(self.users)

    def delete(self, user):
        self.deleted.append(user)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _account(account_id: str, roles: str = "任课教师"):
    return SimpleNamespace(id=account_id, roles=roles, display_name=account_id, email=f"{account_id}@example.com")


class AdminBatchDeleteTests(unittest.TestCase):
    def setUp(self):
        caller = SimpleNamespace(password_hash="hashed", roles="系统管理员")
        self.permission_patch = patch.object(admin, "_check_admin_permission", return_value=caller)
        self.password_patch = patch.object(admin, "verify_password", return_value=True)
        self.permission_patch.start()
        self.password_patch.start()

    def tearDown(self):
        self.password_patch.stop()
        self.permission_patch.stop()

    def test_removes_all_selected_accounts_in_one_commit(self):
        db = _FakeDb([_account("teacher-1"), _account("teacher-2")])

        response = admin.batch_delete_users(
            admin.AdminBatchDeleteRequest(user_ids=["teacher-1", "teacher-2"], caller_password="password"),
            user_id="admin-1",
            db=db,
        )

        self.assertEqual([user.id for user in db.deleted], ["teacher-1", "teacher-2"])
        self.assertTrue(db.committed)
        self.assertEqual(response.data["deleted_count"], 2)

    def test_rejects_the_whole_request_when_it_contains_system_admin(self):
        db = _FakeDb([_account("teacher-1"), _account("protected", "系统管理员")])

        with self.assertRaises(HTTPException) as exc_info:
            admin.batch_delete_users(
                admin.AdminBatchDeleteRequest(user_ids=["teacher-1", "protected"], caller_password="password"),
                user_id="admin-1",
                db=db,
            )

        self.assertEqual(exc_info.exception.status_code, 403)
        self.assertEqual(db.deleted, [])
        self.assertFalse(db.committed)


if __name__ == "__main__":
    unittest.main()
