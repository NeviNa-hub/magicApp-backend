"""定义异步生成任务及其处理结果。"""

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.base import TimestampMixin
from app.db.models.enums import STATUS_CHECK_SQL


class GenerationTask(TimestampMixin, Base):
    """保存任务状态、输入、结果和失败原因。"""

    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    progress: Mapped[int | None] = mapped_column(nullable=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_data: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    cost_points: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("cost_points >= 0", name="ck_generation_tasks_nonnegative_cost"),
        CheckConstraint(
            "progress IS NULL OR (progress >= 0 AND progress <= 100)",
            name="ck_generation_tasks_progress",
        ),
        CheckConstraint(STATUS_CHECK_SQL, name="ck_generation_tasks_status"),
        UniqueConstraint("task_id", name="uq_generation_tasks_task_id"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_tasks_user_idempotency"),
    )
