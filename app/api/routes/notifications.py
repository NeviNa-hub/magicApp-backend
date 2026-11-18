"""当前用户的创作完成通知。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.db.models.work import Work
from app.db.session import get_db

router = APIRouter(prefix="/notifications", tags=["完成通知"])

# 查询完成通知接口
@router.get("", response_model=ApiResponse)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """分页查询本人已完成任务及未读数量。"""
    conditions = (
        GenerationTask.user_id == user.id,
        GenerationTask.status == "completed",
    )
    total = db.scalar(
        select(func.count()).select_from(GenerationTask).where(*conditions)
    )
    unread = db.scalar(
        select(func.count())
        .select_from(GenerationTask)
        .where(*conditions, GenerationTask.notification_read_at.is_(None))
    )
    tasks = db.scalars(
        select(GenerationTask)
        .where(*conditions)
        .order_by(GenerationTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    # 已删除作品没有作品标识；回查时仍校验作品所属用户。
    work_rows = (
        db.execute(
            select(Work.task_id, Work.id)
            .where(
                Work.user_id == user.id,
                Work.status == "completed",
                Work.task_id.in_([task.id for task in tasks]),
            )
            .order_by(Work.id.desc())
        ).all()
        if tasks
        else []
    )
    works_by_task = {}
    for task_id, work_id in work_rows:
        works_by_task.setdefault(task_id, work_id)
    return success(
        {
            "items": [
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "work_id": works_by_task.get(task.id),
                    "title": task.title,
                    "created_at": task.created_at.isoformat(),
                    "is_read": task.notification_read_at is not None,
                }
                for task in tasks
            ],
            "total": total,
            "unread_count": unread,
            "page": page,
            "page_size": page_size,
        }
    )

# 标记完成通知已读接口  
@router.put("/{task_id}/read", response_model=ApiResponse)
def read_notification(
    task_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """将本人已完成任务标记为已读，重复调用保持成功。"""
    task = db.scalar(
        select(GenerationTask).where(
            GenerationTask.task_id == task_id,
            GenerationTask.user_id == user.id,
            GenerationTask.status == "completed",
        )
    )
    if task is None:
        raise ApiError(message="通知不存在", status_code=404)
    if task.notification_read_at is None:
        # 不改变任务更新时间，避免已读操作干扰作品排序。
        db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == task.id,
                GenerationTask.notification_read_at.is_(None),
            )
            .values(
                notification_read_at=func.now(), updated_at=GenerationTask.updated_at
            )
        )
        db.commit()
    return success({"task_id": task_id, "is_read": True})
