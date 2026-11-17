"""个人资料编辑与头像归属测试。"""

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.asset import Asset
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        User.__table__.create(self.engine)
        Asset.__table__.create(self.engine)
        with Session(self.engine) as db:
            db.add(User(id=1, username="原昵称", account="test", password_hash="hash"))
            db.add_all(
                [
                    Asset(
                        id=1,
                        user_id=1,
                        storage_key="one",
                        public_url="/one",
                        original_name="one",
                        content_type="image/png",
                        size_bytes=1,
                    ),
                    Asset(
                        id=2,
                        user_id=2,
                        storage_key="two",
                        public_url="/two",
                        original_name="two",
                        content_type="image/png",
                        size_bytes=1,
                    ),
                ]
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

    def test_update_and_validate_profile(self):
        response = self.client.put(
            "/api/profile", json={"username": " 新昵称 ", "avatar_asset_id": 1}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["username"], "新昵称")
        self.assertEqual(self.client.get("/api/profile").json()["data"]["avatar_asset_id"], 1)
        self.assertEqual(
            self.client.put(
                "/api/profile", json={"username": " ", "avatar_asset_id": 1}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.put(
                "/api/profile", json={"username": "其他", "avatar_asset_id": 2}
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/profile").json()["data"]["username"], "新昵称")
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/api/profile").status_code, 401)


if __name__ == "__main__":
    unittest.main()
