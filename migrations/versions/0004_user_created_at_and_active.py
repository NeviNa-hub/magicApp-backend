"""恢复用户创建时间与停用标记，兼容既有用户行。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_created_at_and_active"
down_revision: str | None = "0003_user_account_and_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增创建时间和停用标记。

    server_default 会让 PostgreSQL 用迁移执行时间回填既有行，
    因此老用户的 created_at 不是真实注册时间，仅作为可用的起始值；
    is_active 默认 true，既有用户不会被停用。
    """
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    """移除本轮新增的字段。"""
    op.drop_column("users", "is_active")
    op.drop_column("users", "created_at")
