"""视频任务创建和后台归档测试。"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.deps import get_current_user
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app
from app.workers.video_generation import run_one


class VideoTaskTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        for table in (
            Account.__table__,
            PointLedger.__table__,
            GenerationTask.__table__,
            Work.__table__,
        ):
            table.create(self.engine)
        with Session(self.engine) as db:
            db.add(Account(user_id=1, points_balance=5))
            db.commit()

        def db_override():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.key_patch = patch(
            "app.api.routes.video.get_settings",
            return_value=SimpleNamespace(siliconflow_api_key="test"),
        )
        self.key_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.key_patch.stop()
        self.engine.dispose()

    def test_submit_retry_and_worker_completion(self):
        body = {"mode": "text", "prompt": "mountain", "ratio": "16:9"}
        headers = {"Idempotency-Key": "key"}
        response = self.client.post("/api/video/tasks", json=body, headers=headers)
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["data"]["task_id"]
        self.assertEqual(
            self.client.post("/api/video/tasks", json=body, headers=headers).json()[
                "data"
            ]["task_id"],
            task_id,
        )
        self.assertEqual(
            self.client.post(
                "/api/video/tasks", json=body, headers={"Idempotency-Key": "new"}
            ).status_code,
            409,
        )
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with (
            patch("app.workers.video_generation.SessionLocal", factory),
            patch(
                "app.workers.video_generation.submit_video", return_value="provider-id"
            ),
            patch(
                "app.workers.video_generation.get_video_status",
                return_value={
                    "status": "Succeed",
                    "results": {"videos": [{"url": "https://example.com/video.mp4"}]},
                },
            ),
        ):
            self.assertTrue(run_one())
        self.assertEqual(
            self.client.get(f"/api/tasks/{task_id}").json()["data"]["status"],
            "completed",
        )
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Account.points_balance)), 0)
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 1)
            self.assertEqual(db.scalar(select(Work.media_type)), "video")


if __name__ == "__main__":
    unittest.main()
