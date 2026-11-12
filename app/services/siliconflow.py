"""硅基流动图片生成客户端。"""
import json
from urllib.request import Request, urlopen

from app.core.config import get_settings

# 页面画幅与第三方生成尺寸的映射；实际支持情况需以模型接口为准。
SIZES = {"1:1": "1024x1024", "16:9": "1280x720", "9:16": "720x1280", "4:3": "1024x768"}


def generate_image(data: dict) -> str:
    """调用图像生成服务并返回短期有效的图片地址。"""
    body = json.dumps({"model": "Kwai-Kolors/Kolors", "prompt": data["prompt"] + "，" + data["style"],
                       "image_size": SIZES[data["ratio"]]}).encode("utf-8")
    request = Request("https://api.siliconflow.cn/v1/images/generations", data=body, method="POST",
                      headers={"Authorization": "Bearer " + get_settings().siliconflow_api_key,
                               "Content-Type": "application/json"})
    # 使用平台默认水印；返回的地址约一小时后过期，不作为永久文件存储。
    with urlopen(request, timeout=180) as response:
        result = json.load(response)
    url = result["images"][0]["url"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("生成结果地址无效")
    return url
