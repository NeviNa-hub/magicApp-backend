"""保存账号注销后待重试的文件清理任务。"""

import sqlalchemy as sa
from alembic import op

revision = "0016_pending_file_deletions"
down_revision = "0015_video_cover"
branch_labels = None
depends_on = None

# 待清理文件表迁移
def upgrade() -> None:
    """创建不依赖用户记录的待清理文件表。"""
    op.create_table(
        "pending_file_deletions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "storage_key", name="uq_pending_file_deletions_storage_key"
        ),
    )
    op.create_index(
        "ix_pending_file_deletions_next_attempt_at",
        "pending_file_deletions",
        ["next_attempt_at"],
    )

# 待清理文件表回退
def downgrade() -> None:
    """有待清理文件时阻止回退，避免丢失清理任务。"""
    bind = op.get_bind()
    pending_count = bind.execute(
        sa.text("SELECT count(*) FROM pending_file_deletions")
    ).scalar_one()
    if pending_count:
        raise RuntimeError("仍有待清理文件，不能回退迁移")
    op.drop_index(
        "ix_pending_file_deletions_next_attempt_at", table_name="pending_file_deletions"
    )
    op.drop_table("pending_file_deletions")
