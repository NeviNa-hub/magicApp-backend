"""硅基流动视频接口客户端。"""

import json
from urllib.request import Request, urlopen

from app.core.config import get_settings


def _post(path: str, body: dict) -> dict:
    settings = get_settings()
    request = Request(
        f"{settings.siliconflow_base_url.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + settings.siliconflow_api_key,
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=settings.siliconflow_timeout_seconds) as response:
        return json.load(response)


def submit_video(data: dict) -> str:
    """将文字和画幅提交给视频模型，返回第三方请求标识。"""
    result = _post(
        "/video/submit",
        {
            "model": get_settings().siliconflow_video_model,
            "prompt": f"{data['prompt']}\n画幅比例：{data['ratio']}",
            "ratio": data["ratio"],
        },
    )
    request_id = result.get("requestId")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("视频提交响应缺少请求标识")
    return request_id


def get_video_status(request_id: str) -> dict:
    """按第三方请求标识获取视频状态。"""
    return _post("/video/status", {"requestId": request_id})
