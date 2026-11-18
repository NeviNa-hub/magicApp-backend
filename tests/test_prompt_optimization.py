"""提示词优化接口和第三方请求的隔离测试。"""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.services.prompt_optimization import optimize_prompt

# 提示词优化测试
class PromptOptimizationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.settings = SimpleNamespace(
            siliconflow_api_key="test",
            siliconflow_text_model="test-model",
            siliconflow_base_url="https://example.com/v1",
            siliconflow_timeout_seconds=30,
        )
        self.settings_patch = patch(
            "app.api.routes.prompt_optimization.get_settings", return_value=self.settings
        )
        self.settings_patch.start()

    def tearDown(self):
        self.client.close()
        self.settings_patch.stop()
        app.dependency_overrides.clear()

    def test_auth_validation_and_failure(self):
        body = {"task_type": "image", "prompt": "山水"}
        self.assertEqual(self.client.post("/api/prompts/optimize", json=body).status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        with patch(
            "app.api.routes.prompt_optimization.optimize_prompt", return_value="细雨山水"
        ) as model:
            response = self.client.post("/api/prompts/optimize", json=body)
            self.assertEqual(response.json()["data"]["prompt"], "细雨山水")
            model.assert_called_once_with("山水", "image", 400)
        self.assertEqual(
            self.client.post(
                "/api/prompts/optimize", json={**body, "prompt": "山" * 401}
            ).status_code,
            400,
        )
        with patch(
            "app.api.routes.prompt_optimization.optimize_prompt", return_value="😀" * 400
        ):
            accepted = self.client.post(
                "/api/prompts/optimize", json={**body, "prompt": "😀" * 400}
            )
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(len(accepted.json()["data"]["prompt"]), 400)
        self.assertEqual(
            self.client.post(
                "/api/prompts/optimize", json={**body, "prompt": "😀" * 401}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/prompts/optimize", json={**body, "prompt": " "}).status_code, 422
        )
        with patch(
            "app.api.routes.prompt_optimization.optimize_prompt", side_effect=RuntimeError("secret")
        ):
            response = self.client.post("/api/prompts/optimize", json=body)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("secret", response.text)
        with patch("app.api.routes.prompt_optimization.optimize_prompt", return_value="山" * 401):
            self.assertEqual(self.client.post("/api/prompts/optimize", json=body).status_code, 502)

    def test_provider_payload(self):
        data = json.dumps({"choices": [{"message": {"content": " 优化结果 "}}]}).encode()
        with (
            patch("app.services.prompt_optimization.get_settings", return_value=self.settings),
            patch(
                "app.services.prompt_optimization.urlopen", return_value=io.BytesIO(data)
            ) as request,
        ):
            self.assertEqual(optimize_prompt("原文", "video", 1000), "优化结果")
            sent = request.call_args.args[0]
            body = json.loads(sent.data)
            self.assertEqual(sent.full_url, "https://example.com/v1/chat/completions")
            self.assertEqual(body["messages"][1]["content"], "原文")
            self.assertEqual(body["model"], "test-model")
