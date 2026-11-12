"""增加用户级任务幂等键。"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0011_task_idempotency"
down_revision: str | None = "0010_task_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_tasks", sa.Column("idempotency_key", sa.String(128)))
    op.create_unique_constraint("uq_tasks_user_idempotency", "generation_tasks", ["user_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_tasks_user_idempotency", "generation_tasks", type_="unique")
    op.drop_column("generation_tasks", "idempotency_key")
