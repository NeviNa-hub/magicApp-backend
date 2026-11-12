"""文字生图请求及响应。"""

from typing import Literal

from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated


class ImageGenerationInput(BaseModel):
    """创建任务时提交的画面描述与画幅。"""

    # 用户填写的画面描述，去除首尾空白后最多 500 字符。
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    # 画风文案会与提示词一起发送给生成模型。
    style: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    # 画幅比例由服务端映射为模型的图片尺寸。
    ratio: Literal["1:1", "16:9", "9:16", "4:3"] = "1:1"


class ImageGenerationResult(BaseModel):
    """任务创建响应。"""

    task_id: str = Field(description="任务标识")
    status: str = Field(description="任务状态")
