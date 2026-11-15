"""创作积分定价：按输入与输出 token 估算任务费用。

图片与视频接口不返回真实 token 用量，因此用每类任务的输出规模折算固定预算，
再叠加按提示词实时估算的输入 token。服务端是唯一计价来源，前端只展示
`/pricing/quote` 的结果；创建任务时复用同一函数扣费。
"""

import math
import re
from dataclasses import dataclass

# 每 1000 token 折算 2 积分，并设置 1 积分起扣，避免极短提示词免费。
POINTS_PER_1K_TOKENS = 2
MIN_TASK_POINTS = 1

# 三类任务单次生成折算的输出 token 预算，保持与原有固定价格基本一致。
OUTPUT_TOKEN_BUDGETS = {
    "image": 900,
    "optimization": 450,
    "video": 2200,
}

CJK_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)


@dataclass(frozen=True)
class TaskQuote:
    """一次创作任务的 token 与积分报价。"""

    task_type: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_points: int
    points_per_1k_tokens: int

    def as_dict(self) -> dict:
        """转换为接口响应字段。"""
        return {
            "task_type": self.task_type,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_points": self.cost_points,
            "points_per_1k_tokens": self.points_per_1k_tokens,
        }


def estimate_text_tokens(text: str) -> int:
    """估算文本 token 数：中日韩字符约 1 字 1 token，其余按 4 字符 1 token。"""
    if not text:
        return 0

    cjk_count = len(CJK_PATTERN.findall(text))
    return cjk_count + math.ceil((len(text) - cjk_count) / 4)


def quote_task(task_type: str, prompt: str = "", style: str = "") -> TaskQuote:
    """按任务类型、提示词和画风计算 token 与积分。"""
    output_tokens = OUTPUT_TOKEN_BUDGETS.get(task_type)
    if output_tokens is None:
        raise ValueError(f"不支持的任务类型：{task_type}")

    input_tokens = estimate_text_tokens(prompt) + estimate_text_tokens(style)
    total_tokens = input_tokens + output_tokens
    # 积分只随 token 增长，不设价格上限；提示词长度由请求 schema 限制为 1000 字符。
    cost_points = max(
        MIN_TASK_POINTS,
        math.ceil(total_tokens * POINTS_PER_1K_TOKENS / 1000),
    )

    return TaskQuote(
        task_type=task_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_points=cost_points,
        points_per_1k_tokens=POINTS_PER_1K_TOKENS,
    )
