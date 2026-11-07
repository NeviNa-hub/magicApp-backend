"""定义所有数据库模型共用的基类。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """数据库模型统一继承此基类。"""
