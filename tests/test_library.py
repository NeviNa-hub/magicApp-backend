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
            db.add_all(
                [
                    GenerationTask(
                        id=1,
                        task_id="one",
                        user_id=1,
                        task_type="image",
                        status="processing",
                        input_data={"prompt": "本人任务"},
                        cost_points=2,
                    ),
                    GenerationTask(
                        id=2,
                        task_id="other",
                        user_id=2,
                        task_type="image",
                        status="pending",
                        input_data={"prompt": "他人任务"},
                        cost_points=2,
                    ),
                    GenerationTask(
                        id=3,
                        task_id="failed",
                        user_id=1,
                        task_type="image",
                        status="failed",
                        input_data={},
                        cost_points=2,
                    ),
                    GenerationTask(
                        id=4,
                        task_id="draft",
                        user_id=1,
                        task_type="image",
                        status="canceled",
                        input_data={"prompt": "已取消的草稿"},
                        cost_points=2,
                    ),
                    Work(
                        id=1,
                        user_id=1,
                        title="本人作品",
                        status="completed",
                        media_type="image",
                        media_url="https://example.com/a",
                    ),
                    Work(
                        id=2,
                        user_id=2,
                        title="他人作品",
                        status="completed",
                        media_type="image",
                    ),
                ]
            )
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
        self.assertEqual(data["page_info"]["total"], 3)
        self.assertEqual([tab["count"] for tab in data["tabs"]], [3, 1, 1, 1])
        second = self.client.get("/api/library?page_size=1&page=2").json()["data"]
        self.assertNotEqual(data["lists"][0]["work_id"], second["lists"][0]["work_id"])
        creating = self.client.get("/api/library?status=creating").json()["data"]
        self.assertEqual(creating["lists"][0]["task_id"], "one")
        self.assertEqual(creating["lists"][0]["work_id"], -1)
        self.assertEqual(creating["lists"][0]["status"], "creating")
        # 取消的任务进入草稿，仍可在作品库中查看。
        draft = self.client.get("/api/library?status=draft").json()["data"]
        self.assertEqual(len(draft["lists"]), 1)
        self.assertEqual(draft["lists"][0]["task_id"], "draft")
        self.assertEqual(draft["lists"][0]["title"], "已取消的草稿")
        self.assertEqual(draft["lists"][0]["status"], "draft")
        self.assertEqual(
            self.client.get("/api/library?status=completed").json()["data"]["lists"][0]["title"],
            "本人作品",
        )
        self.assertEqual(self.client.get("/api/library?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/library?status=unknown").status_code, 422)

    def test_search_type_sort_and_pagination(self):
        with Session(self.engine) as db:
            db.get(Work, 1).task_id = 1
            db.add(
                GenerationTask(
                    id=5,
                    task_id="video",
                    user_id=1,
                    task_type="video",
                    status="processing",
                    input_data={"prompt": "山水视频"},
                    cost_points=2,
                )
            )
            db.commit()
        result = self.client.get(
            "/api/library", params={"keyword": "本人任务", "type": "image"}
        ).json()["data"]
        self.assertEqual(result["page_info"]["total"], 2)
        self.assertEqual([tab["count"] for tab in result["tabs"]], [4, 1, 2, 1])
        self.assertEqual(
            self.client.get("/api/library", params={"keyword": "%"}).json()["data"]["page_info"][
                "total"
            ],
            0,
        )
        video = self.client.get("/api/library", params={"type": "video", "sort": "oldest"}).json()[
            "data"
        ]
        self.assertEqual(video["page_info"]["total"], 1)
        self.assertEqual(video["lists"][0]["task_id"], "video")
        self.assertEqual(self.client.get("/api/library?sort=invalid").status_code, 422)

    def test_sort_and_filtered_page_order(self):
        # 相同时间按主键稳定排序，跨页不会重复或遗漏。
        newest = [
            self.client.get("/api/library", params={"page": page, "page_size": 1}).json()["data"][
                "lists"
            ][0]["work_id"]
            for page in range(1, 4)
        ]
        oldest = [
            self.client.get(
                "/api/library", params={"page": page, "page_size": 1, "sort": "oldest"}
            ).json()["data"]["lists"][0]["work_id"]
            for page in range(1, 4)
        ]
        self.assertEqual(set(newest), {1, -1, -4})
        self.assertEqual(set(oldest), set(newest))
        for order in (newest, oldest):
            self.assertEqual(len(order), len(set(order)))
        result = self.client.get(
            "/api/library", params={"keyword": "本人", "status": "completed"}
        ).json()["data"]
        self.assertEqual(result["page_info"]["total"], 1)
        self.assertEqual(result["lists"][0]["title"], "本人作品")

    def test_update_title_validation_and_isolation(self):
        response = self.client.put("/api/library/works/1", json={"title": "  新标题  "})
        self.assertEqual(response.json()["data"], {"work_id": 1, "title": "新标题"})
        self.assertEqual(
            self.client.put("/api/library/works/2", json={"title": "越权"}).status_code, 404
        )
        self.assertEqual(
            self.client.put("/api/library/works/1", json={"title": "  "}).status_code, 422
        )
        self.assertEqual(
            self.client.put("/api/library/works/1", json={"title": "a" * 51}).status_code, 422
        )
        del app.dependency_overrides[get_current_user]
        self.assertEqual(
            self.client.put("/api/library/works/1", json={"title": "标题"}).status_code, 401
        )

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
        self.assertEqual(response.json()["code"], 404)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(Work, 2))

    def test_delete_work_requires_authentication(self):
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.delete("/api/library/works/1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
