"""记录账号删除后仍需清理的本地文件。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 待清理文件模型
class PendingFileDeletion(Base):
    """保留独立于用户的清理任务，供 worker 在失败后重试。"""

    __tablename__ = "pending_file_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_pending_file_deletions_storage_key"),
        Index("ix_pending_file_deletions_next_attempt_at", "next_attempt_at"),
    )
