"""生成任务查询服务。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models.task import GenerationTask


def get_user_task(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """仅查询当前用户的任务，避免泄露其他用户的任务是否存在。"""
    task = db.scalar(
        select(GenerationTask).where(
            GenerationTask.task_id == task_id,
            GenerationTask.user_id == user_id,
        )
    )
    if task is None:
        raise ApiError(code=40402, message="任务不存在", status_code=404)
    return task
