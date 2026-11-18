"""硅基流动文本模型客户端。"""

import json
from urllib.request import Request, urlopen

from app.core.config import get_settings

TASK_NAMES = {"image": "文字生图", "optimization": "图片优化", "video": "文字生视频"}


# 提示词优化服务
def optimize_prompt(prompt: str, task_type: str, limit: int) -> str:
    """发送创作描述并读取模型输出，不记录输入和密钥。"""
    settings = get_settings()
    payload = {
        "model": settings.siliconflow_text_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"你是创作提示词编辑助手。请保留用户原意，改善{TASK_NAMES[task_type]}描述，"
                    f"输出不超过{limit}字的纯文本，不要解释、标题或引号。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "enable_thinking": False,
        "max_tokens": 1024,
        "temperature": 0.5,
    }
    request = Request(
        f"{settings.siliconflow_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.siliconflow_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(
        request, timeout=min(settings.siliconflow_timeout_seconds, 45)
    ) as response:
        body = json.load(response)
    content = body["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("invalid response")
    return content.strip()
