"""积分查询接口的数据格式。"""

from datetime import datetime

from pydantic import BaseModel


class PointLedgerItem(BaseModel):
    """一条积分使用流水。"""

    ledger_id: int
    # delta 为负数表示本次消耗积分。
    delta: int
    balance_after: int
    reason: str
    reference_id: str | None
    created_at: datetime


class PointsSummaryResult(BaseModel):
    """当前余额、累计已用积分和分页后的使用流水。"""

    points_balance: int
    used_points: int
    page: int
    page_size: int
    total: int
    items: list[PointLedgerItem]
