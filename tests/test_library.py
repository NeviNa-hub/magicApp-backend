"""作品库筛选、分页与用户隔离测试（SQLite 测试数据）。"""

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        GenerationTask.__table__.create(self.engine)
        Work.__table__.create(self.engine)
        with Session(self.engine) as db:
            db.add_all([
                GenerationTask(id=1, task_id="one", user_id=1, task_type="image", status="processing", input_data={"prompt": "本人任务"}, cost_points=2),
                GenerationTask(id=2, task_id="other", user_id=2, task_type="image", status="pending", input_data={"prompt": "他人任务"}, cost_points=2),
                GenerationTask(id=3, task_id="failed", user_id=1, task_type="image", status="failed", input_data={}, cost_points=2),
                Work(id=1, user_id=1, title="本人作品", status="completed", media_type="image", media_url="https://example.com/a"),
                Work(id=2, user_id=2, title="他人作品", status="completed", media_type="image"),
            ])
            db.commit()
        def get_test_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = get_test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_filter_pagination_and_isolation(self):
        data = self.client.get("/api/library?page_size=1").json()["data"]
        self.assertEqual(data["page_info"]["total"], 2)
        self.assertEqual([tab["count"] for tab in data["tabs"]], [2, 1, 1, 0])
        second = self.client.get("/api/library?page_size=1&page=2").json()["data"]
        self.assertNotEqual(data["lists"][0]["work_id"], second["lists"][0]["work_id"])
        creating = self.client.get("/api/library?status=creating").json()["data"]
        self.assertEqual(creating["lists"][0]["task_id"], "one")
        self.assertEqual(creating["lists"][0]["work_id"], -1)
        self.assertEqual(self.client.get("/api/library?status=draft").json()["data"]["lists"], [])
        self.assertEqual(self.client.get("/api/library?status=completed").json()["data"]["lists"][0]["title"], "本人作品")
        self.assertEqual(self.client.get("/api/library?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/library?status=unknown").status_code, 422)

    def test_authentication_required(self):
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/api/library").status_code, 401)

    def test_delete_own_work(self):
        response = self.client.delete("/api/library/works/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"work_id": 1})
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Work, 1))
        completed = self.client.get("/api/library?status=completed").json()["data"]
        self.assertEqual(completed["lists"], [])
        self.assertEqual(completed["page_info"]["total"], 0)

    def test_delete_other_user_work_returns_not_found(self):
        response = self.client.delete("/api/library/works/2")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 40404)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(Work, 2))

    def test_delete_work_requires_authentication(self):
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.delete("/api/library/works/1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
