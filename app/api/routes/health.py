"""提供服务存活和数据库连通检查接口。"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.core.responses import ApiResponse, success
from app.db.session import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

# 数据库或迁移未就绪沿用现有的服务端错误码。
_NOT_READY_CODE = 50001

_REASON_MESSAGES = {
    "database_unavailable": "数据库暂不可用",
    "metadata_error": "无法读取迁移脚本，请检查服务部署",
    "missing_table": "数据库缺少迁移版本表，请执行 alembic upgrade head",
    "unversioned": "数据库尚未记录迁移版本，请执行 alembic upgrade head",
    "multiple_heads": "数据库迁移存在多个版本头，请检查 alembic heads",
}


@router.get("/health", response_model=ApiResponse)
def get_health() -> ApiResponse:
    """确认 API 服务进程正在运行。

    只做进程存活检查，不访问数据库，迁移期间也不会被判定为死亡。
    """
    return success({"status": "ok"})


@lru_cache(maxsize=1)
def _load_migration_state() -> tuple[tuple[str, ...], frozenset[str]]:
    """解析 alembic 脚本目录，返回 (所有 head, 所有 revision)。

    alembic 只在首次调用时导入，结果被缓存，避免把依赖带进每个就绪检查请求。
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    # health.py 位于 app/api/routes/，parents[3] 即项目根目录。
    project_root = Path(__file__).resolve().parents[3]
    config = Config()
    config.set_main_option("script_location", str(project_root / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = tuple(script.get_heads())
    revisions = frozenset(revision.revision for revision in script.walk_revisions())
    return heads, revisions


def _describe_migration(
    heads: tuple[str, ...], revisions: frozenset[str], connection: Any
) -> dict[str, str | None]:
    """对比数据库版本与脚本 head；一致时返回空字典。"""
    if not heads:
        return {"reason": "metadata_error", "current": None, "expected": None}
    if len(heads) != 1:
        return {"reason": "multiple_heads", "current": None, "expected": None}

    expected = heads[0]

    # alembic_version 在从未迁移过的库里不存在，需要先判断再查询。
    if not inspect(connection).has_table("alembic_version"):
        return {"reason": "missing_table", "current": None, "expected": expected}

    versions = list(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    if not versions:
        return {"reason": "unversioned", "current": None, "expected": expected}
    if len(versions) > 1:
        return {
            "reason": "multiple_heads",
            "current": ", ".join(sorted(versions)),
            "expected": expected,
        }

    current = versions[0]
    if current == expected:
        return {}
    # 版本存在于本地脚本中说明只是落后；找不到则通常是数据库领先于代码。
    if current in revisions:
        return {"reason": "behind", "current": current, "expected": expected}
    return {"reason": "ahead", "current": current, "expected": expected}


def _not_ready(
    reason: str, current: str | None = None, expected: str | None = None
) -> JSONResponse:
    """构造 503 未就绪响应；原因同时写进 message 和 data.reason。"""
    if reason == "behind":
        message = f"数据库迁移版本落后（当前 {current}，期望 {expected}）"
    elif reason == "ahead":
        message = f"数据库迁移版本高于代码（当前 {current}，期望 {expected}）"
    else:
        message = _REASON_MESSAGES.get(reason, "服务未就绪")

    logger.warning(
        "readiness not_ready reason=%s current=%s expected=%s", reason, current, expected
    )
    data = {
        "status": "not_ready",
        "reason": reason,
        "current": current,
        "expected": expected,
    }
    body = ApiResponse(code=_NOT_READY_CODE, message=message, data=data)
    return JSONResponse(status_code=503, content=body.model_dump())


@router.get("/ready", response_model=ApiResponse)
def get_ready() -> ApiResponse | JSONResponse:
    """确认数据库可连接，且迁移版本与代码脚本的 head 一致。"""
    try:
        heads, revisions = _load_migration_state()
    except Exception as error:
        logger.error("readiness metadata_error: %s", type(error).__name__)
        return _not_ready("metadata_error")

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            problem = _describe_migration(heads, revisions, connection)
    except Exception as error:
        # 数据库未启动、密码错误等都在这里兜底；只记录异常类型，不输出连接串。
        logger.warning("readiness database_error: %s", type(error).__name__)
        return _not_ready("database_unavailable")

    if not problem:
        return success({"status": "ready", "database": "ok"})
    return _not_ready(
        problem["reason"] or "database_unavailable",
        problem.get("current"),
        problem.get("expected"),
    )
