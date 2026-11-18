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
from app.db.models.file_deletion import PendingFileDeletion
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app
from app.workers.video_generation import run_one


# 视频任务测试
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
            PendingFileDeletion.__table__,
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

    # 测试草稿创建和删除
    def test_draft_crud_and_insufficient_balance(self):
        payload = {
            "task_type": "video",
            "title": "草稿",
            "input_data": {"prompt": "山", "mode": "text", "ratio": "16:9"},
        }
        draft = self.client.post("/api/drafts", json=payload).json()["data"]
        self.assertEqual(self.client.get("/api/drafts").json()["data"]["total"], 1)
        payload["title"] = "新名称"
        self.assertEqual(
            self.client.put(f"/api/drafts/{draft['id']}", json=payload).json()["data"][
                "title"
            ],
            "新名称",
        )
        with Session(self.engine) as db:
            db.scalar(select(Account).where(Account.user_id == 1)).points_balance = 0
            db.commit()
        body = {**payload["input_data"], "draft_id": draft["id"]}
        self.assertEqual(
            self.client.post(
                "/api/video/tasks", json=body, headers={"Idempotency-Key": "poor"}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.get(f"/api/drafts/{draft['id']}").status_code, 200)
        self.assertEqual(
            self.client.delete(f"/api/drafts/{draft['id']}").status_code, 200
        )
        self.assertEqual(self.client.get(f"/api/drafts/{draft['id']}").status_code, 404)

    def test_draft_submit_is_atomic_and_idempotent(self):
        payload = {
            "task_type": "video",
            "title": "草稿",
            "input_data": {"prompt": "mountain", "mode": "text", "ratio": "16:9"},
        }
        draft = self.client.post("/api/drafts", json=payload).json()["data"]
        body = {**payload["input_data"], "draft_id": draft["id"]}
        headers = {"Idempotency-Key": "draft-key"}
        response = self.client.post("/api/video/tasks", json=body, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["task_id"], draft["id"])
        self.assertEqual(
            self.client.post(
                "/api/video/tasks", json=body, headers=headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/video/tasks", json=body, headers={"Idempotency-Key": "other-key"}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.get(f"/api/drafts/{draft['id']}").status_code, 404)
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 1)

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

    def test_duration_quote_charge_and_provider_payload(self):
        """报价、扣费、模型参数使用同一时长，旧任务按 5 秒兼容。"""
        with Session(self.engine) as db:
            db.scalar(select(Account)).points_balance = 30
            db.commit()
        body = {"mode": "text", "ratio": "16:9", "prompt": "mountain", "duration": 10}
        quote = self.client.post(
            "/api/pricing/quote",
            json={"task_type": "video", "prompt": body["prompt"], "duration": 10},
        ).json()["data"]
        response = self.client.post(
            "/api/video/tasks", json=body, headers={"Idempotency-Key": "duration-10"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["cost_points"], quote["cost_points"])
        with Session(self.engine) as db:
            self.assertEqual(
                db.scalar(select(GenerationTask)).input_data["duration"], 10
            )
        self.assertEqual(
            self.client.post(
                "/api/video/tasks",
                json={**body, "duration": 16},
                headers={"Idempotency-Key": "invalid"},
            ).status_code,
            422,
        )
        from app.services.siliconflow_video import submit_video

        with (
            patch(
                "app.services.siliconflow_video.get_settings",
                return_value=SimpleNamespace(siliconflow_video_model="test"),
            ),
            patch(
                "app.services.siliconflow_video._post", return_value={"requestId": "id"}
            ) as post,
        ):
            submit_video(body)
            self.assertEqual(post.call_args.args[1]["duration"], 10)
            submit_video({"prompt": "old", "ratio": "1:1"})
            self.assertEqual(post.call_args.args[1]["duration"], 5)
        old_body = {"mode": "text", "ratio": "1:1", "prompt": "old"}
        old = self.client.post(
            "/api/video/tasks", json=old_body, headers={"Idempotency-Key": "old-key"}
        )
        self.assertEqual(old.status_code, 200)
        with Session(self.engine) as db:
            task = db.scalar(
                select(GenerationTask).where(
                    GenerationTask.task_id == old.json()["data"]["task_id"]
                )
            )
            task.input_data = {
                key: value
                for key, value in task.input_data.items()
                if key != "duration"
            }
            db.commit()
        repeated = self.client.post(
            "/api/video/tasks", json=old_body, headers={"Idempotency-Key": "old-key"}
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(
            repeated.json()["data"]["task_id"], old.json()["data"]["task_id"]
        )


if __name__ == "__main__":
    unittest.main()
