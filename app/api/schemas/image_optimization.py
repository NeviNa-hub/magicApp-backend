"""图片优化任务的请求与响应字段。"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class ImageOptimizationInput(BaseModel):
    """使用已上传的本人图片创建优化任务。"""

    upload_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=r"^[1-9][0-9]{0,9}$"),
    ] = Field(description="已上传图片的资产标识")
    prompt: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ] = Field(description="优化要求，1–200 字符")


class ImageOptimizationResult(BaseModel):
    """成功创建或幂等重试返回的任务信息。"""

    task_id: str = Field(description="任务的公开标识")
    status: str = Field(description="任务当前状态")
