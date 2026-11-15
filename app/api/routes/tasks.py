"""统一生成任务查询与操作接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.tasks import TaskResult
from app.core.responses import ApiResponse, success
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.db.session import get_db
from app.services.tasks import (
    cancel_user_task,
    get_retry_cost,
    get_user_task,
    retry_user_task,
    task_billing_state,
)

router = APIRouter(prefix="/tasks", tags=["任务"])


def _build_task_result(db: Session, task: GenerationTask) -> dict:
    """按任务状态组装响应；结果地址仅在任务完成后返回。"""
    result = task.result_data if isinstance(task.result_data, dict) else {}
    urls = result.get("result_urls", []) if task.status == "completed" else []
    if not isinstance(urls, list):
        urls = []
    net_paid, refunded = task_billing_state(db, task)
    return TaskResult(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
        progress=100 if task.status == "completed" else task.progress,
        result_urls=[url for url in urls if isinstance(url, str)],
        error_message=task.error_message if task.status == "failed" else None,
        cost_points=task.cost_points,
        refund_points=refunded,
        retry_cost_points=get_retry_cost(task, net_paid, refunded),
    ).model_dump()


@router.get("/{task_id}", response_model=ApiResponse)
def get_task(
    task_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """查询本人任务；结果地址仅在任务完成后返回。"""
    return success(_build_task_result(db, get_user_task(db, user.id, task_id)))


@router.post("/{task_id}/cancel", response_model=ApiResponse)
def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """取消本人进行中的任务，并退回该任务净支付的积分。"""
    return success(_build_task_result(db, cancel_user_task(db, user.id, task_id)))


@router.post("/{task_id}/retry", response_model=ApiResponse)
def retry_task(
    task_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """重新排队本人失败的任务；上次失败已退款时按任务费用再次扣费。"""
    return success(_build_task_result(db, retry_user_task(db, user.id, task_id)))
