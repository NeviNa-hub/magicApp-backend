"""生成任务查询与操作服务。"""

from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models.account import Account, PointLedger
from app.db.models.task import GenerationTask

CANCELABLE_STATUSES = ("pending", "processing")
CANCEL_REFUND_REASON = "task_cancel_refund"
# 模型未产出结果时退回本次扣费；重试重新排队时按任务费用再次扣费。
FAIL_REFUND_REASON = "task_fail_refund"
RETRY_CHARGE_REASON = "task_retry_charge"
REFUND_REASONS = (CANCEL_REFUND_REASON, FAIL_REFUND_REASON)
# 同一任务多次重试/退款时按前缀追加序号，避开流水 (用户, 原因, 标识) 唯一约束。
REFERENCE_SEPARATOR = ":"


def get_user_task(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """仅查询当前用户的任务，避免泄露其他用户的任务是否存在。"""
    task = db.scalar(
        select(GenerationTask).where(
            GenerationTask.task_id == task_id,
            GenerationTask.user_id == user_id,
        )
    )
    if task is None:
        raise ApiError(message="任务不存在", status_code=404)
    return task


def _get_locked_user_task(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """行锁读取本人任务，串行化同一任务的取消与重试操作。"""
    task = db.scalar(
        select(GenerationTask)
        .where(
            GenerationTask.task_id == task_id,
            GenerationTask.user_id == user_id,
        )
        .with_for_update()
    )
    if task is None:
        raise ApiError(message="任务不存在", status_code=404)
    return task


def _get_task_ledgers(db: Session, user_id: int, task_id: str) -> list[PointLedger]:
    """读取任务本身及其重试、退款产生的流水，按任务标识前缀匹配。"""
    reference = PointLedger.reference_id
    return list(
        db.scalars(
            select(PointLedger).where(
                PointLedger.user_id == user_id,
                or_(
                    reference == task_id,
                    reference.like(f"{task_id}{REFERENCE_SEPARATOR}%"),
                ),
            )
        )
    )


def task_billing_state(db: Session, task: GenerationTask) -> tuple[int, int]:
    """返回任务净支付积分和已退回积分，退款时以净支付为上限避免超额退款。"""
    ledgers = _get_task_ledgers(db, task.user_id, task.task_id)
    net_paid = max(-sum(ledger.delta for ledger in ledgers), 0)
    refunded = sum(ledger.delta for ledger in ledgers if ledger.delta > 0)
    return net_paid, refunded


def get_retry_cost(task: GenerationTask, net_paid: int, refunded: int) -> int:
    """计算重试需要扣除的积分：上次失败已退款时按任务费用重新扣费。"""
    if task.status != "failed" or net_paid > 0 or refunded <= 0:
        return 0
    return task.cost_points


def fail_task(
    db: Session, user_id: int, task_pk: int, message: str, refund: bool = False
) -> int:
    """把处理中的任务标记为失败；模型未产出结果时退回本次扣费。

    `task_pk` 为任务主键；`refund` 由调用方根据第三方是否已产出结果决定，
    避免模型已经计费却仍给用户退款。加锁顺序与取消一致（先账户后任务），
    防止并发死锁。
    """
    account = db.scalar(
        select(Account).where(Account.user_id == user_id).with_for_update()
    )
    task = db.get(GenerationTask, task_pk, with_for_update=True)
    if task is None or task.status != "processing":
        return 0

    task.status = "failed"
    task.error_message = message
    refunded = 0
    if refund and account is not None:
        net_paid, _ = task_billing_state(db, task)
        refunded = min(task.cost_points, net_paid)
        if refunded > 0:
            account.points_balance += refunded
            db.add(
                PointLedger(
                    user_id=user_id,
                    delta=refunded,
                    balance_after=account.points_balance,
                    reason=FAIL_REFUND_REASON,
                    reference_id=(
                        f"{task.task_id}{REFERENCE_SEPARATOR}refund:"
                        f"{uuid4().hex[:12]}"
                    ),
                )
            )
    db.commit()
    return refunded


def cancel_user_task(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """取消仍在进行中的任务并退回该任务净支付的积分。"""
    # 先锁账户再锁任务，与创建任务时的加锁顺序一致，避免并发死锁。
    account = db.scalar(
        select(Account).where(Account.user_id == user_id).with_for_update()
    )
    if account is None:
        raise ApiError(message="积分账户不存在", status_code=409)
    task = _get_locked_user_task(db, user_id, task_id)
    # 重复取消直接返回终态，退款流水以任务标识去重，不会二次退积分。
    if task.status == "canceled":
        db.commit()
        return task
    if task.status not in CANCELABLE_STATUSES:
        raise ApiError(message="任务已结束，无法取消", status_code=409)

    task.status = "canceled"
    task.error_message = None
    # 取消状态和退款同一事务提交；后台进程写回结果前会重新校验状态，取消结果不会被覆盖。
    net_paid, _ = task_billing_state(db, task)
    refund_amount = min(task.cost_points, net_paid)
    if refund_amount > 0:
        account.points_balance += refund_amount
        db.add(
            PointLedger(
                user_id=user_id,
                delta=refund_amount,
                balance_after=account.points_balance,
                reason=CANCEL_REFUND_REASON,
                reference_id=task.task_id,
            )
        )
    db.commit()
    return task


def retry_user_task(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """将失败任务重新排队；上次失败已退款时按任务费用重新扣费。"""
    account = db.scalar(
        select(Account).where(Account.user_id == user_id).with_for_update()
    )
    if account is None:
        raise ApiError(message="积分账户不存在", status_code=409)
    task = _get_locked_user_task(db, user_id, task_id)
    if task.status != "failed":
        raise ApiError(message="只有创作失败的任务可以重试", status_code=409)

    if (task.result_data or {}).get("submission_unknown"):
        raise ApiError(message="视频提交结果尚未确认，请联系管理员核查后再重试", status_code=409)

    # 未退款的失败重试免费，保证模型已计费时用户仍能拿到结果。
    net_paid, refunded = task_billing_state(db, task)
    retry_cost = get_retry_cost(task, net_paid, refunded)
    if retry_cost > 0:
        if account.points_balance < retry_cost:
            raise ApiError(message="积分不足，无法重试", status_code=409)
        account.points_balance -= retry_cost
        db.add(
            PointLedger(
                user_id=user_id,
                delta=-retry_cost,
                balance_after=account.points_balance,
                reason=RETRY_CHARGE_REASON,
                reference_id=(
                    f"{task_id}{REFERENCE_SEPARATOR}retry:{uuid4().hex[:12]}"
                ),
            )
        )

    # 清空上次结果与失败原因，后台领取后按原输入重新生成。
    task.status = "pending"
    task.progress = 0
    task.error_message = None
    task.result_data = None
    db.commit()
    return task
