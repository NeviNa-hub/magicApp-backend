"""HTTP 公共依赖：解析 Bearer 令牌并校验登录状态。"""

from datetime import datetime, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import hash_session_token
from app.db.models.session_model import UserSession
from app.db.models.user import User
from app.db.session import get_db

# auto_error=False：缺少或格式错误的 Authorization 头交给我们统一处理，
# 避免 FastAPI 默认的 403 响应绕过项目统一响应格式。
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> ApiError:
    """构造“未登录或会话失效”的统一业务错误。"""
    return ApiError(code=40102, message="未登录或登录已过期", status_code=401)


def _ensure_user_active(user: User) -> None:
    """停用用户拒绝逻辑的唯一接入点。"""
    if not user.is_active:
        raise ApiError(code=40301, message="账号已停用", status_code=403)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> UserSession:
    """校验令牌对应会话存在、未过期且未被撤销，返回该会话。"""
    if credentials is None:
        raise _unauthorized()

    token = credentials.credentials.strip()
    if not token:
        raise _unauthorized()

    # 数据库只保存令牌摘要，查询时按同一摘要比对，不接触明文令牌。
    user_session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if user_session is None:
        raise _unauthorized()
    return user_session


def get_current_user(
    user_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    """返回当前登录用户；受保护接口直接依赖本函数即可。"""
    user = db.get(User, user_session.user_id)
    if user is None:
        raise _unauthorized()
    _ensure_user_active(user)
    return user
