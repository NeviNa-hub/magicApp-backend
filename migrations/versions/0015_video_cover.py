"""为视频作品关联可选封面。"""

import sqlalchemy as sa
from alembic import op

revision = "0015_video_cover"
down_revision = "0014_notification_read"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增可空封面资源关联。"""
    op.add_column("works", sa.Column("cover_asset_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_works_cover_asset",
        "works",
        "assets",
        ["cover_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """移除封面关联。"""
    op.drop_constraint("fk_works_cover_asset", "works", type_="foreignkey")
    op.drop_column("works", "cover_asset_id")
