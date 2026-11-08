"""账号认证接口：处理注册、密码验证和登录会话创建。"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.api.schemas.auth import LoginInput, LoginResult, RegisterInput, RegisterResult
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.core.security import hash_password, hash_session_token, verify_password
from app.db.models.account import DEFAULT_POINTS_BALANCE, Account
from app.db.models.session_model import UserSession
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["账号"])

# 登录接口
@router.post("/login", response_model=ApiResponse)
def login_user(
    payload: LoginInput,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """校验账号密码并创建一个有过期时间的登录会话。

    账号不存在、密码错误、账号停用分别返回不同业务码，便于前端引导。
    """
    user = db.scalar(select(User).where(User.account == payload.account))
    if user is None:
        raise ApiError(code=40103, message="账号不存在，请注册", status_code=401)
    if not verify_password(payload.password, user.password_hash):
        raise ApiError(code=40101, message="密码错误", status_code=401)

    # 停用账号不签发会话；先校验密码，避免错误密码也能探出停用状态。
    if not user.is_active:
        raise ApiError(code=40301, message="账号已停用", status_code=403)

    # 随机令牌只返回给客户端；数据库仅保存其摘要，避免数据库泄露即可直接冒用令牌。
    access_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=get_settings().session_expire_days
    )
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(access_token),
        expires_at=expires_at,
    )
    db.add(user_session)
    db.commit()

    return success(
        LoginResult(
            access_token=access_token,
            expires_at=expires_at,
            user_id=user.id,
            username=user.username,
            account=user.account,
        ).model_dump()
    )


# 注册接口
@router.post("/register", response_model=ApiResponse)
def register_user(
    payload: RegisterInput,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """创建新账号，并以哈希形式保存密码。"""
    existing_user = db.scalar(select(User).where(User.account == payload.account))
    if existing_user:
        raise ApiError(code=40902, message="账号已注册", status_code=409)

    user = User(
        username=payload.username,
        account=payload.account,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        # flush 先分配自增 id，余额行与用户在同一事务内提交：
        # 任一步失败都会整体回滚，不会留下“有用户但没有余额行”的中间态。
        db.flush()  # 分配自增 id
        db.add(Account(user_id=user.id, points_balance=DEFAULT_POINTS_BALANCE))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ApiError(code=40902, message="账号已注册", status_code=409) from error

    # flush 时已回填自增 id；commit 后对象仍在会话中，可直接构造公开响应。
    return success(
        RegisterResult(
            user_id=user.id,
            username=user.username,
            account=user.account,
        ).model_dump()
    )


# 登出接口
@router.post("/logout", response_model=ApiResponse)
def logout_user(
    user_session: UserSession = Depends(get_current_session),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """撤销当前令牌对应的会话。

    令牌无效、已过期或已撤销时统一返回 401（code=40102），
    因此重复登出与未登录调用行为一致，不会泄露会话是否存在。
    """
    user_session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return success(message="已退出登录")
