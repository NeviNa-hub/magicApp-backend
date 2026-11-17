"""创作失败退款与重试计费测试。"""

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
from app.services.tasks import fail_task
from app.workers.image_generation import run_one as run_image_task
from app.workers.video_generation import run_one as run_video_task

IMAGE_BODY = {"prompt": "mountain", "style": "ink", "ratio": "1:1"}


class FailureRefundTest(unittest.TestCase):
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

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.client = TestClient(app)
        self.patches = [
            patch(
                "app.api.routes.text_to_image.get_settings",
                return_value=SimpleNamespace(siliconflow_api_key="test"),
            ),
            patch(
                "app.api.routes.video.get_settings",
                return_value=SimpleNamespace(siliconflow_api_key="test"),
            ),
            patch("app.workers.image_generation.SessionLocal", self.session_factory),
            patch("app.workers.video_generation.SessionLocal", self.session_factory),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def create_image_task(self, key="image"):
        """创建一次文字生图任务并返回任务标识。"""
        response = self.client.post(
            "/api/text-to-image/tasks",
            json=IMAGE_BODY,
            headers={"Idempotency-Key": key},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]["task_id"]

    def balance(self):
        """读取当前用户余额。"""
        with Session(self.engine) as db:
            return db.scalar(select(Account.points_balance))

    def reason_ledgers(self, reason):
        """按原因读取积分流水。"""
        with Session(self.engine) as db:
            return list(
                db.scalars(select(PointLedger).where(PointLedger.reason == reason))
            )
        
    # 测试草稿转换为图片任务
    def test_draft_conversion_image(self):
        data = {"prompt": "mountain", "style": "ink", "ratio": "1:1"}
        response = self.client.post(
            "/api/drafts",
            json={"task_type": "image", "title": "草稿", "input_data": data},
        )
        self.assertEqual(response.status_code, 200)
        draft_id = response.json()["data"]["id"]
        payload = {**data, "draft_id": draft_id}
        response = self.client.post(
            "/api/text-to-image/tasks",
            json=payload,
            headers={"Idempotency-Key": "draft-test"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["task_id"], draft_id)
        self.assertEqual(
            self.client.post(
                "/api/text-to-image/tasks",
                json=payload,
                headers={"Idempotency-Key": "draft-test"},
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(f"/api/drafts/{draft_id}").status_code, 404)
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 1)

    def test_provider_failure_refunds_once(self):
        task_id = self.create_image_task()
        self.assertEqual(self.balance(), 3)

        with patch(
            "app.workers.image_generation.generate_image",
            side_effect=ValueError("provider failure"),
        ):
            self.assertTrue(run_image_task())

        status = self.client.get(f"/api/tasks/{task_id}").json()["data"]
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["refund_points"], 2)
        self.assertEqual(status["retry_cost_points"], 2)
        self.assertEqual(self.balance(), 5)

        refunds = self.reason_ledgers("task_fail_refund")
        self.assertEqual(len(refunds), 1)
        self.assertEqual(refunds[0].delta, 2)

        # 重复标记失败不会二次退款
        with Session(self.engine) as db:
            task = db.scalar(select(GenerationTask))
            self.assertEqual(fail_task(db, 1, task.id, "重复标记", refund=True), 0)
        self.assertEqual(self.balance(), 5)
        self.assertEqual(len(self.reason_ledgers("task_fail_refund")), 1)

        summary = self.client.get("/api/points/myInfo").json()["data"]
        self.assertEqual(summary["used_points"], 0)
        self.assertIn(
            (2, "task_fail_refund"),
            [(item["delta"], item["reason"]) for item in summary["items"]],
        )

    def test_archive_failure_keeps_charge_and_retry_is_free(self):
        task_id = self.create_image_task()

        with (
            patch(
                "app.workers.image_generation.generate_image",
                return_value="https://example.com/ok.png",
            ),
            patch(
                "app.workers.image_generation.Work",
                side_effect=RuntimeError("archive failed"),
            ),
        ):
            self.assertTrue(run_image_task())

        status = self.client.get(f"/api/tasks/{task_id}").json()["data"]
        self.assertEqual(status["status"], "failed")
        # 模型已产出图片，第三方已计费，不回退积分；重试不再扣费
        self.assertEqual(status["refund_points"], 0)
        self.assertEqual(status["retry_cost_points"], 0)
        self.assertEqual(self.balance(), 3)

        retry = self.client.post(f"/api/tasks/{task_id}/retry")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["data"]["status"], "pending")
        self.assertEqual(self.balance(), 3)

    def test_retry_after_refund_charges_again(self):
        task_id = self.create_image_task()

        with patch(
            "app.workers.image_generation.generate_image",
            side_effect=ValueError("provider failure"),
        ):
            self.assertTrue(run_image_task())
        self.assertEqual(self.balance(), 5)

        retry = self.client.post(f"/api/tasks/{task_id}/retry")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["data"]["status"], "pending")
        self.assertEqual(retry.json()["data"]["retry_cost_points"], 0)
        self.assertEqual(self.balance(), 3)

        charges = self.reason_ledgers("task_retry_charge")
        self.assertEqual(len(charges), 1)
        self.assertEqual(charges[0].delta, -2)

        # 再次失败同样退款，流水按尝试追加标识，不会被唯一约束挡住
        with patch(
            "app.workers.image_generation.generate_image",
            side_effect=ValueError("provider failure again"),
        ):
            self.assertTrue(run_image_task())
        self.assertEqual(self.balance(), 5)
        self.assertEqual(len(self.reason_ledgers("task_fail_refund")), 2)

        # 余额不足时拒绝重试且不扣费
        with Session(self.engine) as db:
            db.scalar(select(Account)).points_balance = 0
            db.commit()
        insufficient = self.client.post(f"/api/tasks/{task_id}/retry")
        self.assertEqual(insufficient.status_code, 409)
        self.assertEqual(insufficient.json()["code"], 409)
        self.assertEqual(self.balance(), 0)

    def test_video_failure_refunds(self):
        body = {"mode": "text", "prompt": "mountain", "ratio": "16:9"}
        response = self.client.post(
            "/api/video/tasks", json=body, headers={"Idempotency-Key": "video"}
        )
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["data"]["task_id"]
        self.assertEqual(self.balance(), 0)

        with (
            patch(
                "app.workers.video_generation.submit_video",
                return_value="provider-1",
            ),
            patch(
                "app.workers.video_generation.get_video_status",
                return_value={"status": "Failed"},
            ),
        ):
            self.assertTrue(run_video_task())

        status = self.client.get(f"/api/tasks/{task_id}").json()["data"]
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["refund_points"], 5)
        self.assertEqual(status["retry_cost_points"], 5)
        self.assertEqual(self.balance(), 5)


if __name__ == "__main__":
    unittest.main()
