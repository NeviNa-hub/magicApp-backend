"""定义用户资料信息：用户名用于展示，账号用于登录，密码只保存哈希。"""

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

# 导入所有数据表共用的基类。继承它的类会被 SQLAlchemy 识别为数据库模型
from app.db.base import Base  
# users 用户表结构。
# 用 SQLAlchemy 把 Python 类映射成数据库表：类代表表，类里的字段代表表中的列

# 定义一个名为 User 的模型类。它继承 Base，所以 SQLAlchemy 会把它映射成数据库表
class User(Base):
    """保存用户名、唯一登录账号和密码哈希，不保存明文密码。"""

    __tablename__ = "users"

# Mapped[...] 表示该属性是一个数据库映射字段，`mapped_column(...)` 描述数据库列的类型和约束
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)  # 用户名，不能为空
    account: Mapped[str] = mapped_column(String(64), nullable=False)  # 登录账号，不能为空;`account` 在 Python 中是字符串，在数据库中对应一个最长 64 个字符、不能为空的列
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


    # __table_args__ 定义表级规则   
    __table_args__ = (
        UniqueConstraint("account", name="uq_users_account"),  #账号不能重复
        Index("ix_users_account", "account"), #给账号建立索引，便于按账号快速查询
    )
