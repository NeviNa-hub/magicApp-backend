"""图片上传、校验和访问权限测试。"""

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models.asset import Asset
from app.db.session import get_db
from app.main import app


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        self.path_patch = patch(
            "app.services.uploads._storage_dir", return_value=self.directory
        )
        self.path_patch.start()
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Asset.__table__.create(self.engine)

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.client = TestClient(app)
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
        self.image = buffer.getvalue()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_upload_and_owner_only_access(self):
        response = self.client.post(
            "/api/uploads/images",
            files={"file": ("../sample.png", self.image, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["name"], "sample.png")
        response = self.client.get(data["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.image)
        self.assertEqual(response.headers["content-type"], "image/png")
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2)
        self.assertEqual(self.client.get(data["url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/uploads/images/999").status_code, 404)
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get(data["url"]).status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/uploads/images", files={"file": ("x.png", self.image)}
            ).status_code,
            401,
        )

    def test_reject_invalid_empty_and_oversize_without_orphans(self):
        for data, expected in [
            (b"", 400),
            (b"not an image", 400),
            (b"x" * (5 * 1024 * 1024 + 1), 413),
        ]:
            response = self.client.post(
                "/api/uploads/images", files={"file": ("x.png", data, "image/png")}
            )
            self.assertEqual(response.status_code, expected)
        self.assertEqual(list(self.directory.iterdir()), [])
        with Session(self.engine) as db:
            self.assertEqual(db.query(Asset).count(), 0)


if __name__ == "__main__":
    unittest.main()
