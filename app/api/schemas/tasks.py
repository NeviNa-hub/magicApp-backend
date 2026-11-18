"""生成任务对外响应结构。"""

from pydantic import BaseModel, Field

# 查询任务接口数据格式
class TaskResult(BaseModel):
    """统一任务查询响应。"""

    task_id: str = Field(description="任务的公开标识")
    task_type: str = Field(description="任务类型，例如 image")
    status: str = Field(
        description="任务状态：pending、processing、completed、failed 或 canceled"
    )
    progress: int | None = Field(description="生成进度，0–100；未知时为 null")
    original_upload_id: str | None = Field(
        default=None, description="图片优化任务的原图资源标识"
    )
    result_urls: list[str] = Field(
        description="完成后的结果地址；生成图片链接约一小时有效"
    )
    error_message: str | None = Field(description="任务失败时的提示，其余状态为 null")
    cost_points: int = Field(
        description="创建任务时实际扣除的积分，取消后展示已退回金额"
    )
    refund_points: int = Field(
        description="该任务已退回的积分总额，含取消退款与失败退款"
    )
    current_refund_points: int = Field(description="本次失败或取消已退回的积分")
    retry_cost_points: int = Field(
        description="重试将扣除的积分；上次失败已退款时为原任务费用，其余为 0"
    )
