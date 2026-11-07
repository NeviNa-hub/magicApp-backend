"""定义作品库中的用户作品。"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.base import TimestampMixin


class Work(TimestampMixin, Base):
    """保存作品信息，并关联生成来源任务。"""

    __tablename__ = "works"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_tasks.task_id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), index=True)
    media_url: Mapped[str | None] = mapped_column(String(2048))
    media_type: Mapped[str] = mapped_column(String(24), nullable=False, server_default="image")
