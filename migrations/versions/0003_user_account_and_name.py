"""区分用户展示名称和登录账号，并保留已有账号数据。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_account_and_name"
down_revision: str | None = "0002_simplify_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将旧 username 改作登录账号，并新增独立用户名字段。"""
    op.alter_column("users", "username", new_column_name="account")
    op.execute("ALTER TABLE users RENAME CONSTRAINT uq_users_username TO uq_users_account")
    op.execute("ALTER INDEX ix_users_username RENAME TO ix_users_account")

    # 先允许空值，回填旧用户后再设为必填，避免升级时丢失或阻断已有数据。
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.execute("UPDATE users SET username = account")
    op.alter_column("users", "username", nullable=False)


def downgrade() -> None:
    """回退时删除独立用户名，并恢复旧的 username 登录账号列。"""
    op.drop_column("users", "username")
    op.execute("ALTER INDEX ix_users_account RENAME TO ix_users_username")
    op.execute("ALTER TABLE users RENAME CONSTRAINT uq_users_account TO uq_users_username")
    op.alter_column("users", "account", new_column_name="username")
