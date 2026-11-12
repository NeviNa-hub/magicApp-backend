"""文字生视频创建和积分事务。"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.video import VideoTaskInput
from app.core.errors import ApiError
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask


def create_video_task(
    db: Session, user_id: int, key: str, payload: VideoTaskInput
) -> GenerationTask:
    """锁定账户后进行幂等检查、扣费并创建任务。"""
    account = db.scalar(
        select(Account).where(Account.user_id == user_id).with_for_update()
    )
    if account is None:
        raise ApiError(code=40901, message="积分账户不存在", status_code=409)
    data = payload.model_dump()
    existing = db.scalar(
        select(GenerationTask).where(
            GenerationTask.user_id == user_id, GenerationTask.idempotency_key == key
        )
    )
    if existing:
        if existing.task_type != "video" or existing.input_data != data:
            raise ApiError(
                code=40903, message="幂等标识已用于其他请求", status_code=409
            )
        return existing
    if account.points_balance < 5:
        raise ApiError(code=40901, message="积分不足", status_code=409)
    account.points_balance -= 5
    task = GenerationTask(
        task_id=uuid4().hex,
        user_id=user_id,
        idempotency_key=key,
        task_type="video",
        status="pending",
        input_data=data,
        cost_points=5,
    )
    db.add(task)
    db.add(
        PointLedger(
            user_id=user_id,
            delta=-5,
            balance_after=account.points_balance,
            reason="video_generation",
            reference_id=task.task_id,
        )
    )
    db.commit()
    return task
