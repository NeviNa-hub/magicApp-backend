"""把 accounts 余额列默认值从 0 调整为 100，仅影响新插入的行。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_accounts_default_points_100"
down_revision: str | None = "0007_works_task_fk_to_pk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """修改列默认值；已有余额行保持不变，不回填历史用户。"""
    op.alter_column(
        "accounts",
        "points_balance",
        existing_type=sa.BigInteger(),
        server_default=sa.text("100"),
    )


def downgrade() -> None:
    """恢复为 0；已有余额行同样保持不变。"""
    op.alter_column(
        "accounts",
        "points_balance",
        existing_type=sa.BigInteger(),
        server_default=sa.text("0"),
    )
