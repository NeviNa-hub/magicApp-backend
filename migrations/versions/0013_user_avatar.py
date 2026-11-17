"""为用户资料关联本人上传的头像。"""

import sqlalchemy as sa
from alembic import op

revision = "0013_user_avatar"
down_revision = "0012_task_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增可选头像资产关联。"""
    op.add_column("users", sa.Column("avatar_asset_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_avatar_asset", "users", "assets", ["avatar_asset_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """移除头像关联，不删除已上传文件。"""
    op.drop_constraint("fk_users_avatar_asset", "users", type_="foreignkey")
    op.drop_column("users", "avatar_asset_id")
