"""硅基流动图片生成客户端。"""

import json
from urllib.request import Request, urlopen

from app.core.config import get_settings


def generate_image(data: dict) -> str:
    """读取模型配置，生成图片并返回短期有效的地址。"""
    settings = get_settings()
    sizes = {
        "1:1": settings.siliconflow_image_size_square,
        "16:9": settings.siliconflow_image_size_landscape,
        "9:16": settings.siliconflow_image_size_portrait,
        "4:3": settings.siliconflow_image_size_classic,
    }
    body = json.dumps(
        {
            "model": settings.siliconflow_image_model,
            "prompt": f"{data['prompt']}\n画风：{data['style']}\n画幅比例：{data['ratio']}",
            "image_size": sizes[data["ratio"]],
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
    # 不关闭服务商默认水印；返回地址不是永久存储。
    with urlopen(request, timeout=settings.siliconflow_timeout_seconds) as response:
        result = json.load(response)
    url = result["images"][0]["url"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("生成结果地址无效")
    return url
