"""模型客户端读取环境配置的测试。"""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.siliconflow import generate_image
from app.services.siliconflow_image_edit import optimize_image


class ModelConfigTest(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            siliconflow_base_url="https://example.com/v1/",
            siliconflow_api_key="test-key",
            siliconflow_image_model="test-image-model",
            siliconflow_image_edit_model="test-edit-model",
            siliconflow_timeout_seconds=42,
            siliconflow_image_size_square="512x512",
            siliconflow_image_size_landscape="1280x720",
            siliconflow_image_size_portrait="720x1280",
            siliconflow_image_size_classic="1024x768",
        )

    def test_clients_use_configured_values(self):
        for module, operation, expected_model in (
            (
                "app.services.siliconflow",
                lambda: generate_image({"prompt": "x", "style": "y", "ratio": "1:1"}),
                "test-image-model",
            ),
            (
                "app.services.siliconflow_image_edit",
                lambda: optimize_image(b"png", "image/png", "edit"),
                "test-edit-model",
            ),
        ):
            with (
                self.subTest(module=module),
                patch(f"{module}.get_settings", return_value=self.settings),
                patch(
                    f"{module}.urlopen",
                    return_value=io.BytesIO(
                        b'{"images":[{"url":"https://example.com/result"}]}'
                    ),
                ) as request,
            ):
                self.assertEqual(operation(), "https://example.com/result")
                argument = request.call_args.args[0]
                payload = json.loads(argument.data)
                self.assertEqual(
                    argument.full_url, "https://example.com/v1/images/generations"
                )
                self.assertEqual(payload["model"], expected_model)
                self.assertEqual(request.call_args.kwargs["timeout"], 42)
                if module.endswith("siliconflow"):
                    self.assertEqual(payload["image_size"], "512x512")
                    self.assertIn("x", payload["prompt"])
                    self.assertIn("y", payload["prompt"])
                    self.assertIn("1:1", payload["prompt"])


if __name__ == "__main__":
    unittest.main()
