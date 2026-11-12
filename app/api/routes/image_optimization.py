"""图片优化任务接口。"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.image_optimization import (
    ImageOptimizationInput,
    ImageOptimizationResult,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.db.session import get_db
from app.services.image_optimization import create_optimization_task

router = APIRouter(prefix="/image-optimization", tags=["图片优化"])


@router.post("/tasks", response_model=ApiResponse)
def create_task(
    payload: ImageOptimizationInput,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """创建图片优化任务并扣除 1 积分，重复请求应使用原幂等键。"""
    if not idempotency_key.strip():
        raise ApiError(code=40001, message="幂等标识不能为空", status_code=400)
    if not get_settings().siliconflow_api_key.strip():
        raise ApiError(code=50302, message="图片优化服务尚未配置", status_code=503)
    task = create_optimization_task(db, user.id, idempotency_key, payload)
    return success(
        ImageOptimizationResult(task_id=task.task_id, status=task.status).model_dump()
    )
