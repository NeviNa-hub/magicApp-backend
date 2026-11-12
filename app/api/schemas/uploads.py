"""图片上传响应结构。"""

from pydantic import BaseModel, Field


class UploadedImageResult(BaseModel):
    """上传成功后的资产标识和本人访问地址。"""

    upload_id: str = Field(description="上传资产标识，用于后续图片任务")
    url: str = Field(description="需要 Bearer 令牌的图片访问路径")
    name: str = Field(description="处理后的原文件名")
