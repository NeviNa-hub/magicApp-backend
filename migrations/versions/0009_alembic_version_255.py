"""扩宽 alembic_version.version_num，避免较长的 revision id 写入失败。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_alembic_version_255"
down_revision: str | None = "0008_accounts_default_points_100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """version_num 从 VARCHAR(32) 扩到 VARCHAR(255)。"""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    """恢复 VARCHAR(32)；库中若存在超过 32 字符的版本号，回退会失败。"""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
