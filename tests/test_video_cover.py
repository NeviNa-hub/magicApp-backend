"""视频封面选择与用户隔离测试。"""

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.asset import Asset
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import get_db
from app.main import app


# 视频封面测试
class VideoCoverTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        for table in (Asset.__table__, GenerationTask.__table__, Work.__table__):
            table.create(self.engine)
        with Session(self.engine) as db:
            for asset_id, user_id in ((1, 1), (2, 2)):
                db.add(
                    Asset(
                        id=asset_id,
                        user_id=user_id,
                        storage_key=str(asset_id),
                        public_url="/x",
                        original_name="x",
                        content_type="image/png",
                        size_bytes=1,
                    )
                )
            db.add_all(
                [
                    Work(
                        id=1,
                        user_id=1,
                        title="视频",
                        status="completed",
                        media_type="video",
                        media_url="https://example.com/video",
                    ),
                    Work(
                        id=2,
                        user_id=1,
                        title="图片",
                        status="completed",
                        media_type="image",
                        media_url="https://example.com/image",
                    ),
                    Work(
                        id=3,
                        user_id=2,
                        title="他人视频",
                        status="completed",
                        media_type="video",
                        media_url="https://example.com/video",
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

    def test_cover_ownership_and_removal(self):
        self.assertEqual(
            self.client.put(
                "/api/library/works/1/cover", json={"cover_asset_id": 2}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(
                "/api/library/works/2/cover", json={"cover_asset_id": 1}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(
                "/api/library/works/3/cover", json={"cover_asset_id": 1}
            ).status_code,
            404,
        )
        result = self.client.put(
            "/api/library/works/1/cover", json={"cover_asset_id": 1}
        )
        self.assertEqual(result.json()["data"]["cover_asset_id"], 1)
        self.assertEqual(
            self.client.get("/api/library/works/1/media").json()["data"][
                "cover_asset_id"
            ],
            1,
        )
        items = self.client.get("/api/library").json()["data"]["lists"]
        self.assertEqual(
            next(item for item in items if item["work_id"] == 1)["cover_asset_id"], 1
        )
        result = self.client.put(
            "/api/library/works/1/cover", json={"cover_asset_id": None}
        )
        self.assertIsNone(result.json()["data"]["cover_asset_id"])
