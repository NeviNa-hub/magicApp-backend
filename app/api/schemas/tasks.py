"""生成任务对外响应结构。"""

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    """统一任务查询响应。"""

    task_id: str = Field(description="任务的公开标识")
    task_type: str = Field(description="任务类型，例如 image")
    status: str = Field(description="任务状态：pending、processing、completed、failed 或 canceled")
    progress: int | None = Field(description="生成进度，0–100；未知时为 null")
    result_urls: list[str] = Field(description="完成后的结果地址；生成图片链接约一小时有效")
    error_message: str | None = Field(description="任务失败时的提示，其余状态为 null")
