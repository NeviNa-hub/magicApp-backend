"""作品库查询响应。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LibraryPageInfo(BaseModel):
    """当前筛选条件下的分页信息。"""

    page: int = Field(description="当前页码，从 1 开始")
    page_size: int = Field(description="每页条数")
    total: int = Field(description="当前筛选状态的总条数")


# 作品库项数据格式
class LibraryItem(BaseModel):
    """一条已完成作品、创作中任务、已取消任务或编辑草稿。"""

    work_id: int = Field(
        description="作品主键；任务记录为任务主键的负数，仅用于列表标识"
    )
    task_id: str | None = Field(description="来源任务的公开标识")
    title: str = Field(description="作品标题或任务描述")
    status: str = Field(description="completed、creating、canceled 或 draft")
    type_name: str = Field(description="创作类型名称")
    created_at: datetime = Field(description="作品或任务的创建时间")
    cover_asset_id: int | None = None
    media_url: str | None = Field(description="结果媒体地址；可能过期，创作中为空")


# 作品库分页响应数据格式
class LibraryResult(BaseModel):
    """作品库分页响应。"""

    page_info: LibraryPageInfo
    lists: list[LibraryItem]


# 修改作品标题接口数据格式
class UpdateWorkTitle(BaseModel):
    """修改作品标题的请求。"""

    title: str = Field(min_length=1, max_length=50)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: object) -> object:
        """去掉标题首尾空白，再执行长度校验。"""
        return value.strip() if isinstance(value, str) else value


# 修改作品封面接口数据格式
class UpdateWorkCover(BaseModel):
    """选择本人上传的图片作为视频封面，null 表示移除。"""

    cover_asset_id: int | None = Field(ge=1)
