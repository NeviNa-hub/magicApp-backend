"""文字生视频任务的请求与响应结构。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class VideoTaskInput(BaseModel):
    """仅支持文字生视频；图生视频暂不开放。"""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["text"] = Field(description="仅支持 text 文字生视频")
    ratio: Literal["1:1", "9:16", "16:9"] = Field(description="页面支持的画面比例")
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ] = Field(description="视频内容描述，1–300 字符")


class VideoTaskResult(BaseModel):
    """视频任务创建结果。"""

    task_id: str = Field(description="任务公开标识")
    status: str = Field(description="当前任务状态")
