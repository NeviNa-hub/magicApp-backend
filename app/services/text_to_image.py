"""文字生图创建及积分事务。"""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.text_to_image import ImageGenerationInput
from app.core.errors import ApiError
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask

COST = 2


def create_image_task(db: Session, user_id: int, key: str, payload: ImageGenerationInput) -> GenerationTask:
    """锁定账户后处理幂等、扣费和任务写入。"""
    # 同一用户的创建请求在账户行锁上串行，避免并发重复扣费。
    account = db.scalar(select(Account).where(Account.user_id == user_id).with_for_update())
    if account is None:
        raise ApiError(code=40901, message="积分账户不存在", status_code=409)
    data = payload.model_dump()
    # 重试使用相同幂等键返回原任务；不同参数复用同一键则拒绝。
    existing = db.scalar(select(GenerationTask).where(
        GenerationTask.user_id == user_id, GenerationTask.idempotency_key == key
    ))
    if existing:
        if existing.task_type != "image" or existing.input_data != data:
            raise ApiError(code=40903, message="幂等标识已用于其他请求", status_code=409)
        return existing
    if account.points_balance < COST:
        raise ApiError(code=40901, message="积分不足", status_code=409)
    # 余额、任务和流水在同一次提交中落库，任一步失败均不会单独生效。
    account.points_balance -= COST
    task = GenerationTask(task_id=uuid4().hex, user_id=user_id, idempotency_key=key,
                          task_type="image", status="pending", input_data=data, cost_points=COST)
    db.add(task)
    db.add(PointLedger(user_id=user_id, delta=-COST, balance_after=account.points_balance,
                       reason="image_generation", reference_id=task.task_id))
    db.commit()
    return task
