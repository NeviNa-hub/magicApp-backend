"""创建数据库连接，并为每个请求提供独立会话。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.database_connect_timeout},
    pool_timeout=settings.database_connect_timeout,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """提供请求级数据库会话，并在请求结束时关闭。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
