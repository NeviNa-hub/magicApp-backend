"""文字生视频创建和积分事务。"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.video import VideoTaskInput
from app.core.errors import ApiError
from app.core.pricing import quote_task
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask

# 视频任务创建服务
def create_video_task(
    db: Session, user_id: int, key: str, payload: VideoTaskInput
) -> GenerationTask:
    """锁定账户后进行幂等检查、扣费并创建任务。"""
    account = db.scalar(
        select(Account).where(Account.user_id == user_id).with_for_update()
    )
    if account is None:
        raise ApiError(message="积分账户不存在", status_code=409)
    data = payload.model_dump()
    existing = db.scalar(
        select(GenerationTask).where(
            GenerationTask.user_id == user_id, GenerationTask.idempotency_key == key
        )
    )
    if existing:
        # 旧任务没有 duration，按模型原默认 5 秒比较幂等参数。
        existing_data = dict(existing.input_data)
        existing_data.setdefault("duration", 5)
        if existing.task_type != "video" or existing_data != data:
            raise ApiError(message="幂等标识已用于其他请求", status_code=409)
        return existing
    # 视频输出规模占主要成本，提示词 token 在其基础上叠加。
    quote = quote_task("video", payload.prompt, duration=payload.duration)
    if account.points_balance < quote.cost_points:
        raise ApiError(message="积分不足", status_code=409)
    account.points_balance -= quote.cost_points
    if payload.draft_id:
        # 账户锁和草稿锁共同防止重复扣费及重复提交。
        task = db.scalar(
            select(GenerationTask)
            .where(
                GenerationTask.user_id == user_id,
                GenerationTask.task_id == payload.draft_id,
                GenerationTask.task_type == "video",
                GenerationTask.status == "draft",
            )
            .with_for_update()
        )
        if task is None:
            raise ApiError(message="草稿不存在或已提交", status_code=409)
        task.idempotency_key = key
        task.status = "pending"
        task.input_data = data
        task.cost_points = quote.cost_points
    else:
        task = GenerationTask(
            task_id=uuid4().hex,
            user_id=user_id,
            idempotency_key=key,
            task_type="video",
            status="pending",
            input_data=data,
            cost_points=quote.cost_points,
        )
    db.add(task)
    db.add(
        PointLedger(
            user_id=user_id,
            delta=-quote.cost_points,
            balance_after=account.points_balance,
            reason="video_generation",
            reference_id=task.task_id,
        )
    )
    db.commit()
    return task
