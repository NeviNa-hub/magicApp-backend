"""文字生视频任务的请求与响应结构。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# 创建视频任务接口数据格式
class VideoTaskInput(BaseModel):
    """仅支持文字生视频；图生视频暂不开放。"""

    draft_id: str | None = Field(default=None, max_length=128, exclude=True)

    model_config = ConfigDict(extra="forbid")

    duration: int = Field(
        default=5, ge=5, le=15, strict=True, description="视频时长，5 至 15 秒"
    )
    mode: Literal["text"] = Field(description="仅支持 text 文字生视频")
    ratio: Literal["1:1", "9:16", "16:9"] = Field(description="页面支持的画面比例")
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ] = Field(description="视频内容描述，1–1000 字符")


# 查询视频任务接口数据格式
class VideoTaskResult(BaseModel):
    """视频任务创建结果。"""

    task_id: str = Field(description="任务公开标识")
    status: str = Field(description="当前任务状态")
    cost_points: int = Field(description="本次任务实际扣除的积分")
