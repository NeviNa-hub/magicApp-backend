"""为任务添加编辑草稿状态和标题。"""

import sqlalchemy as sa
from alembic import op

revision = "0012_task_drafts"
down_revision = "0011_task_idempotency"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("generation_tasks", sa.Column("title", sa.String(50), nullable=True))
    op.drop_constraint("ck_generation_tasks_status", "generation_tasks", type_="check")
    op.create_check_constraint(
        "ck_generation_tasks_status",
        "generation_tasks",
        "status IN ('draft', 'pending', 'processing', 'completed', 'failed', 'canceled')",
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT count(*) FROM generation_tasks WHERE status = 'draft'")
    ).scalar_one():
        raise RuntimeError("存在草稿，无法回退迁移")
    op.drop_constraint("ck_generation_tasks_status", "generation_tasks", type_="check")
    op.create_check_constraint(
        "ck_generation_tasks_status",
        "generation_tasks",
        "status IN ('pending', 'processing', 'completed', 'failed', 'canceled')",
    )
    op.drop_column("generation_tasks", "title")
