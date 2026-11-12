"""图片优化扣费、幂等与文件归属测试。"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.account import Account, PointLedger
from app.db.models.asset import Asset
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.workers.image_generation import run_one
from app.db.session import get_db
from app.main import app


class OptimizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        (self.directory / "a.png").write_bytes(b"image")
        self.path_patch = patch(
            "app.services.uploads._storage_dir", return_value=self.directory
        )
        self.path_patch.start()
        self.key_patch = patch("app.api.routes.image_optimization.get_settings")
        self.key_patch.start().return_value.siliconflow_api_key = "test"
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        for table in (
            Account.__table__,
            PointLedger.__table__,
            Asset.__table__,
            GenerationTask.__table__,
            Work.__table__,
        ):
            table.create(self.engine)
        with Session(self.engine) as db:
            db.add_all(
                [
                    Account(user_id=1, points_balance=2),
                    Asset(
                        id=1,
                        user_id=1,
                        storage_key="a.png",
                        public_url="/a",
                        original_name="a.png",
                        content_type="image/png",
                        size_bytes=5,
                    ),
                    Asset(
                        id=2,
                        user_id=2,
                        storage_key="other.png",
                        public_url="/b",
                        original_name="b.png",
                        content_type="image/png",
                        size_bytes=5,
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
        self.key_patch.stop()
        self.path_patch.stop()
        self.temp.cleanup()

    def test_creation_idempotency_and_insufficient_balance(self):
        payload = {"upload_id": "1", "prompt": "提高画质"}
        response = self.client.post(
            "/api/image-optimization/tasks",
            json=payload,
            headers={"Idempotency-Key": "abc"},
        )
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["data"]["task_id"]
        retry = self.client.post(
            "/api/image-optimization/tasks",
            json=payload,
            headers={"Idempotency-Key": "abc"},
        )
        self.assertEqual(retry.json()["data"]["task_id"], task_id)
        conflict = self.client.post(
            "/api/image-optimization/tasks",
            json={**payload, "prompt": "其他"},
            headers={"Idempotency-Key": "abc"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(
            self.client.post(
                "/api/image-optimization/tasks",
                json={**payload, "upload_id": "2"},
                headers={"Idempotency-Key": "other"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/image-optimization/tasks",
                json=payload,
                headers={"Idempotency-Key": "second"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/image-optimization/tasks",
                json=payload,
                headers={"Idempotency-Key": "third"},
            ).status_code,
            409,
        )
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Account.points_balance)), 0)
            self.assertEqual(len(db.scalars(select(PointLedger)).all()), 2)
            self.assertEqual(len(db.scalars(select(GenerationTask)).all()), 2)

    def test_worker_archives_result_and_reports_failure(self):
        payload = {"upload_id": "1", "prompt": "enhance"}
        response = self.client.post(
            "/api/image-optimization/tasks",
            json=payload,
            headers={"Idempotency-Key": "worker"},
        )
        task_id = response.json()["data"]["task_id"]
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with (
            patch("app.workers.image_generation.SessionLocal", factory),
            patch(
                "app.workers.image_generation.optimize_image",
                return_value="https://example.com/result.png",
            ) as provider,
        ):
            self.assertTrue(run_one())
            provider.assert_called_once_with(b"image", "image/png", "enhance")
        status = self.client.get(f"/api/tasks/{task_id}").json()["data"]
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["result_urls"], ["https://example.com/result.png"])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Work)).all()), 1)
        second = self.client.post(
            "/api/image-optimization/tasks",
            json=payload,
            headers={"Idempotency-Key": "failure"},
        ).json()["data"]["task_id"]
        with (
            patch("app.workers.image_generation.SessionLocal", factory),
            patch(
                "app.workers.image_generation.optimize_image",
                side_effect=ValueError("provider failure"),
            ),
        ):
            self.assertTrue(run_one())
        status = self.client.get(f"/api/tasks/{second}").json()["data"]
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error_message"], "图片生成失败，请稍后重试")

    def test_authentication_and_validation(self):
        self.assertEqual(
            self.client.post(
                "/api/image-optimization/tasks",
                json={"upload_id": "0", "prompt": "x"},
                headers={"Idempotency-Key": "a"},
            ).status_code,
            422,
        )
        del app.dependency_overrides[get_current_user]
        self.assertEqual(
            self.client.post(
                "/api/image-optimization/tasks",
                json={"upload_id": "1", "prompt": "x"},
                headers={"Idempotency-Key": "a"},
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
