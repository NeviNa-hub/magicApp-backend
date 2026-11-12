"""文字生视频请求字段校验。"""

import unittest
from pydantic import ValidationError
from app.api.schemas.video import VideoTaskInput


class VideoSchemaTest(unittest.TestCase):
    def test_text_mode(self):
        result = VideoTaskInput(mode="text", ratio="16:9", prompt="  mountain  ")
        self.assertEqual(result.prompt, "mountain")

    def test_invalid_requests(self):
        for payload in (
            {"mode": "image", "ratio": "1:1", "prompt": "x", "upload_id": "1"},
            {"mode": "text", "ratio": "1:1", "prompt": " "},
            {"mode": "text", "ratio": "2:1", "prompt": "x"},
            {"mode": "text", "ratio": "1:1", "prompt": "x", "fps": 60},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                VideoTaskInput(**payload)


if __name__ == "__main__":
    unittest.main()
