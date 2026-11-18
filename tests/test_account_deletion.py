"""账号永久注销的校验、隔离和文件清理测试。"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.models.account import Account, PointLedger
from app.db.models.asset import Asset
from app.db.models.file_deletion import PendingFileDeletion
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app
from app.services.file_deletions import cleanup_pending_file_deletions

# 账号注销测试
class AccountDeletionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        event.listen(
            self.engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all(
                [
                    User(
                        id=1,
                        username="一",
                        account="user_one",
                        password_hash=hash_password("password1"),
                    ),
                    User(
                        id=2,
                        username="二",
                        account="user_two",
                        password_hash=hash_password("password2"),
                    ),
                ]
            )
            db.flush()
            db.add_all(
                [
                    Account(user_id=1, points_balance=5),
                    Account(user_id=2, points_balance=7),
                ]
            )
            db.add_all(
                [
                    Asset(
                        id=1,
                        user_id=1,
                        storage_key="one.png",
                        public_url="/one",
                        original_name="one",
                        content_type="image/png",
                        size_bytes=1,
                    ),
                    Asset(
                        id=3,
                        user_id=1,
                        storage_key="one-second.png",
                        public_url="/one-second",
                        original_name="one-second",
                        content_type="image/png",
                        size_bytes=1,
                    ),
                    Asset(
                        id=2,
                        user_id=2,
                        storage_key="two.png",
                        public_url="/two",
                        original_name="two",
                        content_type="image/png",
                        size_bytes=1,
                    ),
                ]
            )
            db.add(
                GenerationTask(
                    id=1,
                    task_id="pending",
                    user_id=1,
                    task_type="image",
                    status="pending",
                    input_data={},
                )
            )
            db.add(
                Work(
                    id=1,
                    user_id=1,
                    title="作品",
                    status="completed",
                    media_type="image",
                )
            )
            db.add(
                PointLedger(
                    user_id=1,
                    delta=-1,
                    balance_after=5,
                    reason="test",
                    reference_id="x",
                )
            )
            db.commit()
        for name in ("one.png", "one-second.png", "two.png"):
            (Path(self.temp.name) / name).write_bytes(b"x")

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.settings_patch = patch(
            "app.services.uploads.get_settings",
            return_value=SimpleNamespace(upload_dir=self.temp.name),
        )
        self.settings_patch.start()
        self.client = TestClient(app, raise_server_exceptions=False)
        self.token = self.client.post(
            "/api/auth/login", json={"account": "user_one", "password": "password1"}
        ).json()["data"]["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.settings_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_password_active_task_and_deletion(self):
        url = "/api/auth/delete-account"
        self.assertEqual(
            self.client.post(url, json={"password": "password1"}).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                url, headers=self.headers, json={"password": "wrong"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url, headers=self.headers, json={"password": "password1"}
            ).status_code,
            409,
        )
        self.assertTrue((Path(self.temp.name) / "one.png").exists())
        with Session(self.engine) as db:
            db.get(GenerationTask, 1).status = "canceled"
            db.commit()
        self.assertEqual(
            self.client.post(
                url, headers=self.headers, json={"password": "password1"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/profile", headers=self.headers).status_code, 401
        )
        self.assertFalse((Path(self.temp.name) / "one.png").exists())
        self.assertFalse((Path(self.temp.name) / "one-second.png").exists())
        self.assertTrue((Path(self.temp.name) / "two.png").exists())
        with Session(self.engine) as db:
            self.assertIsNone(db.get(User, 1))
            self.assertIsNotNone(db.get(User, 2))
            self.assertEqual(db.scalars(select(Work)).all(), [])
            self.assertEqual(db.scalars(select(PointLedger)).all(), [])
            self.assertEqual(db.scalars(select(GenerationTask)).all(), [])
            self.assertEqual(db.scalars(select(Asset.id)).all(), [2])

    def test_partial_file_isolation_failure_restores_previous_files(self):
        """多个文件中途隔离失败时，已处理文件恢复原位。"""
        with Session(self.engine) as db:
            db.get(GenerationTask, 1).status = "canceled"
            db.commit()

        path_type = type(Path(self.temp.name))
        original_rename = path_type.rename

        def fail_second_file(path, target):
            if path.name == "one-second.png":
                raise OSError("disk error")
            return original_rename(path, target)

        with patch.object(path_type, "rename", new=fail_second_file):
            response = self.client.post(
                "/api/auth/delete-account",
                headers=self.headers,
                json={"password": "password1"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertTrue((Path(self.temp.name) / "one.png").exists())
        self.assertTrue((Path(self.temp.name) / "two.png").exists())
        self.assertFalse((Path(self.temp.name) / ".one.png.deleting").exists())
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, 1))
            self.assertIsNotNone(db.get(Asset, 1))

    def test_post_commit_file_cleanup_failure_retries_from_queue(self):
        """提交注销后文件删除失败会保留任务并由 worker 重试。"""
        with Session(self.engine) as db:
            db.get(GenerationTask, 1).status = "canceled"
            db.commit()

        path_type = type(Path(self.temp.name))
        original_unlink = path_type.unlink

        def fail_one_quarantine(path, *args, **kwargs):
            if path.name == ".one.png.deleting":
                raise OSError("disk error")
            return original_unlink(path, *args, **kwargs)

        with patch.object(path_type, "unlink", new=fail_one_quarantine):
            response = self.client.post(
                "/api/auth/delete-account",
                headers=self.headers,
                json={"password": "password1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue((Path(self.temp.name) / ".one.png.deleting").exists())
        with Session(self.engine) as db:
            self.assertIsNone(db.get(User, 1))
            self.assertIsNone(db.get(Asset, 1))
            pending = db.scalar(select(PendingFileDeletion))
            self.assertIsNotNone(pending)
            self.assertEqual(pending.attempts, 1)
            pending.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            cleaned = cleanup_pending_file_deletions(db, storage_keys=["one.png"])
            self.assertEqual(cleaned, 1)
            self.assertIsNone(db.scalar(select(PendingFileDeletion)))
        self.assertFalse((Path(self.temp.name) / ".one.png.deleting").exists())

    def test_database_commit_failure_restores_files(self):
        """数据库提交失败时，恢复已隔离的上传文件。"""
        with Session(self.engine) as db:
            db.get(GenerationTask, 1).status = "canceled"
            db.commit()

        with patch(
            "sqlalchemy.orm.Session.commit", side_effect=RuntimeError("db error")
        ):
            response = self.client.post(
                "/api/auth/delete-account",
                headers=self.headers,
                json={"password": "password1"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertTrue((Path(self.temp.name) / "one.png").exists())
        self.assertFalse((Path(self.temp.name) / ".one.png.deleting").exists())
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, 1))
            self.assertIsNotNone(db.get(Asset, 1))

    def test_file_isolation_failure_keeps_account(self):
        """文件隔离失败不能返回注销成功。"""
        with Session(self.engine) as db:
            db.get(GenerationTask, 1).status = "canceled"
            db.commit()
        with patch.object(
            type(Path(self.temp.name)), "rename", side_effect=OSError("disk error")
        ):
            response = self.client.post(
                "/api/auth/delete-account",
                headers=self.headers,
                json={"password": "password1"},
            )
        self.assertEqual(response.status_code, 500)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, 1))
            self.assertIsNotNone(db.get(Asset, 1))
