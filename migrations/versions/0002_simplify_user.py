"""第二版数据库结构：用户表精简为主键、账号和密码哈希。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_simplify_user"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """移除首版暂时不需要的用户状态和时间字段。"""
    op.drop_column("users", "is_active")
    op.drop_column("users", "created_at")
    op.drop_column("users", "updated_at")


def downgrade() -> None:
    """回滚时恢复用户状态和时间字段。"""
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
