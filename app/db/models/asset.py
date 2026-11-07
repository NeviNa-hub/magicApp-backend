"""定义用户上传文件的索引信息。"""

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.base import TimestampMixin


class Asset(TimestampMixin, Base):
    """数据库只保存文件地址和属性，文件内容存放在文件存储中。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    public_url: Mapped[str] = mapped_column(String(2048))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
