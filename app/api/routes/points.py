"""用户积分查询接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.points import PointLedgerItem, PointsSummaryResult
from app.core.responses import ApiResponse, success
from app.db.models.account import Account, PointLedger
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/points", tags=["积分"])


@router.get("/myInfo", response_model=ApiResponse)
def get_my_points(
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse:
    """查询当前用户剩余积分和已使用积分流水。

    分页约定：page 从 1 开始，page_size 默认 20、最大 100；流水按
    created_at 倒序、同一时间按 id 倒序，保证翻页结果稳定。
    """
    points_balance = db.scalar(select(Account.points_balance).where(Account.user_id == user.id))
    # 历史用户可能没有余额行，按 0 返回。
    if points_balance is None:
        points_balance = 0

    # 只统计负数变动：正数流水属于加点，暂不涉及积分回退。
    spent_cond = (PointLedger.user_id == user.id, PointLedger.delta < 0)

    total = db.scalar(select(func.count()).select_from(PointLedger).where(*spent_cond)) or 0
    used_points = (
        db.scalar(select(func.coalesce(-func.sum(PointLedger.delta), 0)).where(*spent_cond)) or 0
    )

    ledgers = db.scalars(
        select(PointLedger)
        .where(*spent_cond)
        .order_by(PointLedger.created_at.desc(), PointLedger.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return success(
        PointsSummaryResult(
            points_balance=points_balance,
            used_points=used_points,
            page=page,
            page_size=page_size,
            total=total,
            items=[
                PointLedgerItem(
                    ledger_id=ledger.id,
                    delta=ledger.delta,
                    balance_after=ledger.balance_after,
                    reason=ledger.reason,
                    reference_id=ledger.reference_id,
                    created_at=ledger.created_at,
                )
                for ledger in ledgers
            ],
        ).model_dump()
    )
