"""为任务和作品的状态字段添加受约束的取值集合。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0006_constrain_status_fields"
down_revision: str | None = "0005_drop_redundant_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 app/db/models/enums.py 保持一致；新增状态必须配一个新迁移。
_STATUS_VALUES = ("pending", "processing", "completed", "failed", "canceled")
_STATUS_IN = ", ".join(f"'{value}'" for value in _STATUS_VALUES)
_STATUS_TABLES = ("generation_tasks", "works")


def _reject_incompatible_rows() -> None:
    """检查历史数据；发现集合外的状态直接中止，避免迁移后写入被静默拒绝。"""
    if context.is_offline_mode():
        # 离线模式只能生成 SQL，无法连库校验，降级为不做数据检查。
        return
    bind = op.get_bind()
    for table in _STATUS_TABLES:
        invalid = bind.execute(
            sa.text(
                f"SELECT DISTINCT status FROM {table} WHERE status NOT IN ({_STATUS_IN})"
            )
        ).scalars().all()
        if invalid:
            raise RuntimeError(
                f"{table}.status 存在约束外的历史值 {sorted(invalid)}；"
                "请先人工映射到允许的状态后重新执行迁移"
            )


def upgrade() -> None:
    """先校验数据，再添加 CHECK 约束。"""
    _reject_incompatible_rows()
    op.create_check_constraint(
        "ck_generation_tasks_status",
        "generation_tasks",
        f"status IN ({_STATUS_IN})",
    )
    op.create_check_constraint(
        "ck_works_status",
        "works",
        f"status IN ({_STATUS_IN})",
    )


def downgrade() -> None:
    """仅移除约束，历史状态字符串保持不变。"""
    op.drop_constraint("ck_works_status", "works", type_="check")
    op.drop_constraint("ck_generation_tasks_status", "generation_tasks", type_="check")
