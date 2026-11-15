"""Token 计价与创作扣费测试。"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.core.pricing import (
    POINTS_PER_1K_TOKENS,
    estimate_text_tokens,
    quote_task,
)
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask
from app.db.session import get_db
from app.main import app


class PricingTest(unittest.TestCase):
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
            db.add(Account(user_id=1, points_balance=4))
            db.commit()

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.key_patch = patch(
            "app.api.routes.text_to_image.get_settings",
            return_value=SimpleNamespace(siliconflow_api_key="test"),
        )
        self.key_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.key_patch.stop()
        self.engine.dispose()

    def test_estimates_cjk_and_ascii_tokens(self):
        self.assertEqual(estimate_text_tokens(""), 0)
        self.assertEqual(estimate_text_tokens("提高画质"), 4)
        self.assertEqual(estimate_text_tokens("mountain"), 2)
        # 2 个中文字符按 1:1 计，空格与 8 个字母按 4:1 向上取整。
        self.assertEqual(estimate_text_tokens("水墨 mountain"), 5)

    def test_short_prompts_keep_original_prices(self):
        image = quote_task("image", "mountain", "ink")
        self.assertEqual(image.output_tokens, 900)
        self.assertEqual(image.cost_points, 2)
        self.assertEqual(quote_task("optimization", "提高画质").cost_points, 1)
        self.assertEqual(quote_task("video", "mountain").cost_points, 5)
        self.assertEqual(quote_task("optimization", "").cost_points, 1)

    def test_long_prompts_cost_more(self):
        short = quote_task("image", "山")
        long = quote_task("image", "山" * 1000, "水" * 64)
        self.assertEqual(long.input_tokens, 1064)
        self.assertEqual(short.cost_points, 2)
        self.assertEqual(long.cost_points, 4)
        self.assertEqual(quote_task("optimization", "画" * 1000).cost_points, 3)
        self.assertEqual(quote_task("video", "画" * 1000).cost_points, 7)

    def test_quote_route_returns_token_breakdown(self):
        response = self.client.post(
            "/api/pricing/quote",
            json={"task_type": "image", "prompt": "提高画质", "style": "宋式水墨"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["task_type"], "image")
        self.assertEqual(data["input_tokens"], 8)
        self.assertEqual(data["output_tokens"], 900)
        self.assertEqual(data["total_tokens"], 908)
        self.assertEqual(data["cost_points"], 2)
        self.assertEqual(data["points_per_1k_tokens"], POINTS_PER_1K_TOKENS)

        invalid = self.client.post(
            "/api/pricing/quote", json={"task_type": "unknown"}
        )
        self.assertEqual(invalid.status_code, 422)

        too_long = self.client.post(
            "/api/pricing/quote",
            json={"task_type": "image", "prompt": "山" * 1001},
        )
        self.assertEqual(too_long.status_code, 422)

    def test_creation_charges_estimated_tokens_and_reports_cost(self):
        # 提示词上限 1000 字时报价 4 积分，账户余额恰好 4，创建后余额归零。
        response = self.client.post(
            "/api/text-to-image/tasks",
            json={"prompt": "山" * 1000, "style": "水" * 64, "ratio": "1:1"},
            headers={"Idempotency-Key": "long-prompt"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["cost_points"], 4)

        detail = self.client.get(f"/api/tasks/{data['task_id']}").json()["data"]
        self.assertEqual(detail["cost_points"], 4)

        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Account.points_balance)), 0)
            task = db.scalar(select(GenerationTask))
            self.assertEqual(task.cost_points, 4)
            ledger = db.scalar(select(PointLedger))
            self.assertEqual(ledger.delta, -4)
            self.assertEqual(ledger.balance_after, 0)


if __name__ == "__main__":
    unittest.main()
