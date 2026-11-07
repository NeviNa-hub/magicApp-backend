"""创建数据库引擎和请求级会话，供路由通过依赖注入使用。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
# 引擎复用连接池；每个请求单独创建 Session，避免跨请求共享事务状态。
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
        # 无论请求成功或异常都关闭会话，释放连接回连接池。
        session.close()
