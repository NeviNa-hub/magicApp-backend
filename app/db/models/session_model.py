"""定义可撤销的用户登录会话。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class UserSession(TimestampMixin, Base):
    """只保存会话令牌摘要，支持过期和主动撤销。"""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped["User"] = relationship("User")

    __table_args__ = (UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),)
