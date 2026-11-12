"""图片优化任务创建和积分处理。"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.image_optimization import ImageOptimizationInput
from app.core.errors import ApiError
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask
from app.services.uploads import get_image

OPTIMIZATION_COST = 1


def create_optimization_task(
    db: Session, user_id: int, key: str, payload: ImageOptimizationInput
) -> GenerationTask:
    """创建本人图片优化任务；余额、任务和流水同一事务提交。"""
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
    # 对同一用户串行校验幂等键，网络重试不会创建新任务或再次扣费。
    if existing:
        if existing.task_type != "optimization" or existing.input_data != data:
            raise ApiError(
                code=40903, message="幂等标识已用于其他请求", status_code=409
            )
        return existing

    # 在扣积分之前验证图片存在并属于当前用户。
    if int(payload.upload_id) > 2_147_483_647:
        raise ApiError(code=40403, message="图片不存在", status_code=404)
    get_image(db, user_id, int(payload.upload_id))
    if account.points_balance < OPTIMIZATION_COST:
        raise ApiError(code=40901, message="积分不足", status_code=409)

    account.points_balance -= OPTIMIZATION_COST
    task = GenerationTask(
        task_id=uuid4().hex,
        user_id=user_id,
        idempotency_key=key,
        task_type="optimization",
        status="pending",
        input_data=data,
        cost_points=OPTIMIZATION_COST,
    )
    db.add(task)
    db.add(
        PointLedger(
            user_id=user_id,
            delta=-OPTIMIZATION_COST,
            balance_after=account.points_balance,
            reason="image_optimization",
            reference_id=task.task_id,
        )
    )
    db.commit()
    return task
