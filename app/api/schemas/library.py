"""作品库查询响应。"""

from datetime import datetime

from pydantic import BaseModel, Field


class LibraryTab(BaseModel):
    """作品库状态及数量。"""

    status: str = Field(description="筛选状态")
    name: str = Field(description="状态显示名称")
    count: int = Field(description="该状态的记录数量")


class LibraryPageInfo(BaseModel):
    """当前筛选条件下的分页信息。"""

    page: int
    page_size: int
    total: int


class LibraryItem(BaseModel):
    """一条已完成作品或创作中任务。"""

    work_id: int = Field(description="作品主键；创作中为任务主键的负数，仅用于列表标识")
    task_id: str | None = Field(description="来源任务的公开标识")
    title: str = Field(description="作品标题或任务描述")
    status: str = Field(description="completed 或 creating")
    type_name: str = Field(description="创作类型名称")
    created_at: datetime = Field(description="作品或任务的创建时间")
    media_url: str | None = Field(description="结果媒体地址；可能过期，创作中为空")


class LibraryResult(BaseModel):
    """作品库分页响应。"""

    tabs: list[LibraryTab]
    page_info: LibraryPageInfo
    lists: list[LibraryItem]
