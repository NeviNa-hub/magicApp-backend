"""创作积分报价的请求与响应结构。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


# 查询创作积分报价接口数据格式
class PricingQuoteInput(BaseModel):
    """按任务类型和提示词查询预计消耗。"""

    task_type: Literal["image", "optimization", "video"] = Field(
        description="任务类型：image、optimization 或 video"
    )
    # 提示词长度上限固定为 800 字符；积分随 token 增长，不设价格上限。
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] = (
        Field(default="", description="提示词，可为空以查询基础价格")
    )
    duration: int = Field(
        default=5, ge=5, le=15, strict=True, description="视频时长，单位秒"
    )
    style: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = (
        Field(default="", description="画风文案，仅文字生图会拼入模型提示词")
    )


# 查询创作积分报价接口数据格式
class PricingQuoteResult(BaseModel):
    """预计 token 与积分消耗。"""

    task_type: str = Field(description="任务类型")
    input_tokens: int = Field(description="按提示词估算的输入 token")
    output_tokens: int = Field(description="该任务折算的输出 token 预算")
    total_tokens: int = Field(description="输入与输出 token 合计")
    cost_points: int = Field(description="预计扣除积分")
    points_per_1k_tokens: int = Field(description="每千 token 折算积分")
