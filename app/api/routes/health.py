"""提供服务存活和数据库连通检查接口。"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.responses import ApiResponse, success
from app.db.session import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=ApiResponse)
def get_health() -> ApiResponse:
    """确认 API 服务进程正在运行。"""
    return success({"status": "ok"})


def check_database() -> bool:
    """用短连接检查数据库，并记录安全的错误摘要。"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as error:
        logger.warning("database readiness check failed: %s", type(error).__name__)
        return False


@router.get("/ready", response_model=ApiResponse)
def get_ready() -> ApiResponse | JSONResponse:
    """确认数据库可连接，供启动检查和运维探活使用。"""
    if not check_database():
        body = ApiResponse(code=50001, message="数据库暂不可用", data=None)
        return JSONResponse(status_code=503, content=body.model_dump())
    return success({"status": "ready", "database": "ok"})
