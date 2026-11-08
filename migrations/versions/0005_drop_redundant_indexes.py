"""删除唯一约束旁重复建立的普通索引，保留唯一性约束本身。"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401  (保持与其他迁移一致的导入风格)
from alembic import op

revision: str = "0005_drop_redundant_indexes"
down_revision: str | None = "0004_user_created_at_and_active"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 这些列已经有 uq_* 唯一约束自带的索引；普通索引纯属重复。
_REDUNDANT_INDEXES = (
    "ix_users_account",
    "ix_user_sessions_token_hash",
    "ix_generation_tasks_task_id",
)


def upgrade() -> None:
    """删除冗余索引；唯一约束（uq_users_account 等）保持不变。"""
    for index_name in _REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    """按 0001 的原始定义恢复普通索引。"""
    op.create_index("ix_users_account", "users", ["account"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])
    op.create_index("ix_generation_tasks_task_id", "generation_tasks", ["task_id"])
