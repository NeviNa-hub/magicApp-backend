"""任务取消与重试操作测试。"""

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask
from app.db.session import get_db
from app.main import app


class TaskActionsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        for table in (
            Account.__table__,
            PointLedger.__table__,
            GenerationTask.__table__,
        ):
            table.create(self.engine)
        with Session(self.engine) as db:
            db.add(Account(user_id=1, points_balance=8))
            db.add(
                PointLedger(
                    user_id=1,
                    delta=-2,
                    balance_after=8,
                    reason="image_generation",
                    reference_id="processing",
                )
            )
            db.add_all(
                [
                    GenerationTask(
                        task_id="processing",
                        user_id=1,
                        task_type="image",
                        status="processing",
                        progress=40,
                        input_data={"prompt": "mountain"},
                        cost_points=2,
                    ),
                    GenerationTask(
                        task_id="failed",
                        user_id=1,
                        task_type="video",
                        status="failed",
                        progress=0,
                        input_data={"prompt": "river"},
                        result_data={"provider_id": "old"},
                        error_message="视频生成失败，请稍后重试",
                        cost_points=5,
                    ),
                    GenerationTask(
                        task_id="completed",
                        user_id=1,
                        task_type="image",
                        status="completed",
                        progress=100,
                        input_data={"prompt": "forest"},
                        result_data={"result_urls": ["https://example.com/ok.png"]},
                        cost_points=2,
                    ),
                    GenerationTask(
                        task_id="other-user",
                        user_id=2,
                        task_type="image",
                        status="processing",
                        progress=10,
                        input_data={"prompt": "hidden"},
                        cost_points=2,
                    ),
                ]
            )
            db.commit()

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_cancel_refunds_points_once(self):
        response = self.client.post("/api/tasks/processing/cancel")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "canceled")
        self.assertEqual(data["result_urls"], [])
        self.assertIsNone(data["error_message"])

        # 重复取消返回同一终态，不产生第二次退款。
        again = self.client.post("/api/tasks/processing/cancel")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["data"]["status"], "canceled")

        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Account.points_balance)), 10)
            ledgers = db.scalars(
                select(PointLedger).where(PointLedger.reason == "task_cancel_refund")
            ).all()
            self.assertEqual(len(ledgers), 1)
            self.assertEqual(ledgers[0].delta, 2)
            self.assertEqual(ledgers[0].balance_after, 10)
            self.assertEqual(ledgers[0].reference_id, "processing")
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 2)
            task = db.scalar(
                select(GenerationTask).where(GenerationTask.task_id == "processing")
            )
            self.assertEqual(task.status, "canceled")

        self.assertEqual(
            self.client.get("/api/tasks/processing").json()["data"]["status"],
            "canceled",
        )

        # 退款后已用积分归零，流水同时保留扣费与退款记录，余额与汇总一致。
        summary = self.client.get("/api/points/myInfo").json()["data"]
        self.assertEqual(summary["points_balance"], 10)
        self.assertEqual(summary["used_points"], 0)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(
            sorted((item["delta"], item["reason"]) for item in summary["items"]),
            [(-2, "image_generation"), (2, "task_cancel_refund")],
        )

    def test_cancel_rejects_finished_task(self):
        response = self.client.post("/api/tasks/completed/cancel")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 409)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Account.points_balance)), 8)
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 1)

    def test_retry_requeues_failed_task_without_charging(self):
        response = self.client.post("/api/tasks/failed/retry")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["progress"], 0)
        self.assertEqual(data["result_urls"], [])
        self.assertIsNone(data["error_message"])

        with Session(self.engine) as db:
            task = db.scalar(
                select(GenerationTask).where(GenerationTask.task_id == "failed")
            )
            self.assertEqual(task.status, "pending")
            self.assertIsNone(task.result_data)
            self.assertIsNone(task.error_message)
            self.assertEqual(task.cost_points, 5)
            self.assertEqual(db.scalar(select(Account.points_balance)), 8)
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 1)

    def test_retry_rejects_active_task(self):
        for task_id in ("processing", "completed"):
            response = self.client.post(f"/api/tasks/{task_id}/retry")
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], 409)

    def test_actions_reject_other_users_tasks(self):
        for action in ("cancel", "retry"):
            response = self.client.post(f"/api/tasks/other-user/{action}")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], 404)


if __name__ == "__main__":
    unittest.main()
