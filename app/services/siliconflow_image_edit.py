"""硅基流动图片编辑客户端。"""

import base64
import json
from urllib.request import Request, urlopen

from app.core.config import get_settings


def optimize_image(image: bytes, content_type: str, prompt: str) -> str:
    """读取私有图片，以 data URL 提交给图片编辑模型并返回临时结果地址。"""
    settings = get_settings()
    image_data = base64.b64encode(image).decode("ascii")
    body = json.dumps(
        {
            "model": settings.siliconflow_image_edit_model,
            "prompt": prompt,
            "image": f"data:{content_type};base64,{image_data}",
        }
    ).encode("utf-8")
    request = Request(
        f"{settings.siliconflow_base_url.rstrip('/')}/images/generations",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + settings.siliconflow_api_key,
            "Content-Type": "application/json",
        },
    )
    # 保留服务端默认水印；结果链接的有效期由服务方决定。
    with urlopen(request, timeout=settings.siliconflow_timeout_seconds) as response:
        result = json.load(response)
    url = result["images"][0]["url"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("图片优化结果地址无效")
    return url
