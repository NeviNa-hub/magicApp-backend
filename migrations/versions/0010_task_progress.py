"""添加任务进度。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_task_progress"
down_revision: str | None = "0009_alembic_version_255"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加可空进度，空值表示进度未知。"""
    op.add_column("generation_tasks", sa.Column("progress", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_generation_tasks_progress", "generation_tasks",
        "progress IS NULL OR (progress >= 0 AND progress <= 100)",
    )


def downgrade() -> None:
    """移除进度字段及约束。"""
    op.drop_constraint("ck_generation_tasks_progress", "generation_tasks", type_="check")
    op.drop_column("generation_tasks", "progress")
