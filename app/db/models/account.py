"""定义用户余额和余额变动流水。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.base import TimestampMixin


class Account(TimestampMixin, Base):
    """每个用户对应一条余额记录。"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    points_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("points_balance >= 0", name="ck_accounts_nonnegative_balance"),
    )


class PointLedger(Base):
    """记录每次加点、扣点或退款，便于追查余额变化。"""

    __tablename__ = "point_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "reason", "reference_id", name="uq_point_ledger_reference"),
    )
