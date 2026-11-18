"""完成通知的归属、分页与已读行为测试。"""

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app

# 通知测试
class NotificationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        User.__table__.create(self.engine)
        GenerationTask.__table__.create(self.engine)
        Work.__table__.create(self.engine)
        with Session(self.engine) as db:
            db.add_all(
                [
                    User(id=1, username="一", account="one", password_hash="hash"),
                    User(id=2, username="二", account="two", password_hash="hash"),
                ]
            )
            db.add_all(
                [
                    GenerationTask(
                        task_id="done-1",
                        user_id=1,
                        task_type="image",
                        status="completed",
                        input_data={},
                    ),
                    GenerationTask(
                        task_id="done-2",
                        user_id=1,
                        task_type="video",
                        status="completed",
                        input_data={},
                    ),
                    GenerationTask(
                        task_id="pending",
                        user_id=1,
                        task_type="image",
                        status="pending",
                        input_data={},
                    ),
                    GenerationTask(
                        task_id="other",
                        user_id=2,
                        task_type="image",
                        status="completed",
                        input_data={},
                    ),
                ]
            )
            db.flush()
            done = db.query(GenerationTask).filter_by(task_id="done-2").one()
            db.add(
                Work(
                    id=10,
                    user_id=1,
                    task_id=done.id,
                    title="本人作品",
                    status="completed",
                    media_type="video",
                )
            )
            db.add(
                Work(
                    id=11,
                    user_id=2,
                    task_id=done.id,
                    title="其他用户作品",
                    status="completed",
                    media_type="video",
                )
            )
            db.commit()

        def test_db():
            with Session(self.engine) as db:
                yield db

        def current_user():
            with Session(self.engine) as db:
                return db.get(User, 1)

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_list_read_and_access_control(self):
        data = self.client.get("/api/notifications?page=1&page_size=1").json()["data"]
        self.assertEqual((data["total"], data["unread_count"], len(data["items"])), (2, 2, 1))
        self.assertEqual(data["items"][0]["task_id"], "done-2")
        self.assertEqual(data["items"][0]["work_id"], 10)
        with Session(self.engine) as db:
            before = db.query(GenerationTask).filter_by(task_id="done-2").one().updated_at
        self.assertEqual(
            self.client.put("/api/notifications/done-2/read", json={}).status_code, 200
        )
        self.assertEqual(
            self.client.put("/api/notifications/done-2/read", json={}).status_code, 200
        )
        with Session(self.engine) as db:
            self.assertEqual(
                before, db.query(GenerationTask).filter_by(task_id="done-2").one().updated_at
            )
        self.assertEqual(self.client.get("/api/notifications").json()["data"]["unread_count"], 1)
        self.assertEqual(self.client.put("/api/notifications/other/read", json={}).status_code, 404)
        self.assertEqual(
            self.client.put("/api/notifications/pending/read", json={}).status_code, 404
        )
        self.assertEqual(self.client.get("/api/notifications?page=0").status_code, 422)
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/api/notifications").status_code, 401)
