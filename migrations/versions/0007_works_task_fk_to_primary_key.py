"""把 works.task_id 从外部字符串引用改为指向 generation_tasks 主键。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0007_works_task_fk_to_primary_key"
down_revision: str | None = "0006_constrain_status_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_all_references_mapped(
    source_column: str, target_column: str, label: str
) -> None:
    """确认 source_column 的非空值都已写入 target_column，否则中止迁移。"""
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    unmapped = bind.execute(
        sa.text(
            f"SELECT count(*) FROM works "
            f"WHERE {source_column} IS NOT NULL AND {target_column} IS NULL"
        )
    ).scalar_one()
    if unmapped:
        raise RuntimeError(
            f"works 表有 {unmapped} 行的 {label} 无法映射，迁移已中止；"
            "请先修复这些引用后重试（未做任何丢弃）"
        )


def upgrade() -> None:
    """新增主键引用列，回填并校验后再替换旧外键列。"""
    op.add_column("works", sa.Column("generation_task_id", sa.Integer(), nullable=True))

    # generation_tasks.task_id 有唯一约束，因此这里是一对一回填。
    op.execute(
        """
        UPDATE works AS w
        SET generation_task_id = gt.id
        FROM generation_tasks AS gt
        WHERE gt.task_id = w.task_id
        """
    )
    _assert_all_references_mapped("task_id", "generation_task_id", "旧 task_id")

    # 删除旧列会连带删除其外键约束与 ix_works_task_id 索引；
    # 引用关系已先写入 generation_task_id，不会丢失。
    op.drop_column("works", "task_id")
    op.alter_column("works", "generation_task_id", new_column_name="task_id")
    op.create_foreign_key(
        "fk_works_task_id_generation_tasks",
        "works",
        "generation_tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_works_task_id", "works", ["task_id"])


def downgrade() -> None:
    """先回填字符串列，再恢复旧的外键定义。"""
    op.add_column("works", sa.Column("legacy_task_id", sa.String(128), nullable=True))

    op.execute(
        """
        UPDATE works AS w
        SET legacy_task_id = gt.task_id
        FROM generation_tasks AS gt
        WHERE gt.id = w.task_id
        """
    )
    _assert_all_references_mapped("task_id", "legacy_task_id", "主键 task_id")

    op.drop_column("works", "task_id")
    op.alter_column("works", "legacy_task_id", new_column_name="task_id")
    op.create_foreign_key(
        "works_task_id_fkey",
        "works",
        "generation_tasks",
        ["task_id"],
        ["task_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_works_task_id", "works", ["task_id"])
