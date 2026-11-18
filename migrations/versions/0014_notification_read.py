"""为完成通知保存已读时间。"""

import sqlalchemy as sa
from alembic import op

revision = "0014_notification_read"
down_revision = "0013_user_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增已读时间，历史已完成任务默认为未读。"""
    op.add_column(
        "generation_tasks",
        sa.Column("notification_read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """移除通知已读时间。"""
    op.drop_column("generation_tasks", "notification_read_at")
