"""统一生成任务查询接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.tasks import TaskResult
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.db.session import get_db
from app.services.tasks import get_user_task

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/{task_id}", response_model=ApiResponse)
def get_task(
    task_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """查询本人任务；结果地址仅在任务完成后返回。"""
    task = get_user_task(db, user.id, task_id)
    result = task.result_data if isinstance(task.result_data, dict) else {}
    urls = result.get("result_urls", []) if task.status == "completed" else []
    if not isinstance(urls, list):
        urls = []
    return success(
        TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            status=task.status,
            progress=100 if task.status == "completed" else task.progress,
            result_urls=[url for url in urls if isinstance(url, str)],
            error_message=task.error_message if task.status == "failed" else None,
        ).model_dump()
    )
