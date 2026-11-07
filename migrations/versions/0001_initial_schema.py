"""创建初始业务表结构。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建初始表结构及用户数据隔离约束。"""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("points_balance", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("points_balance >= 0", name="ck_accounts_nonnegative_balance"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_accounts_user_id"),
    )

    op.create_table(
        "point_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("reference_id", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "reason", "reference_id", name="uq_point_ledger_reference"),
    )
    op.create_index("ix_point_ledger_user_id", "point_ledger", ["user_id"])
    op.create_index("ix_point_ledger_reference_id", "point_ledger", ["reference_id"])

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("public_url", sa.String(2048), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_assets_storage_key"),
    )
    op.create_index("ix_assets_user_id", "assets", ["user_id"])

    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("result_data", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("cost_points", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("cost_points >= 0", name="ck_generation_tasks_nonnegative_cost"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", name="uq_generation_tasks_task_id"),
    )
    op.create_index("ix_generation_tasks_task_id", "generation_tasks", ["task_id"])
    op.create_index("ix_generation_tasks_user_id", "generation_tasks", ["user_id"])
    op.create_index("ix_generation_tasks_task_type", "generation_tasks", ["task_type"])
    op.create_index("ix_generation_tasks_status", "generation_tasks", ["status"])

    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(128)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("media_url", sa.String(2048)),
        sa.Column("media_type", sa.String(24), server_default="image", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["generation_tasks.task_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_works_user_id", "works", ["user_id"])
    op.create_index("ix_works_task_id", "works", ["task_id"])
    op.create_index("ix_works_status", "works", ["status"])


def downgrade() -> None:
    """Drop tables in dependency order."""
    op.drop_table("works")
    op.drop_table("generation_tasks")
    op.drop_table("assets")
    op.drop_table("point_ledger")
    op.drop_table("accounts")
    op.drop_table("user_sessions")
    op.drop_table("users")
