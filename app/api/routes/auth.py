"""账号认证接口：处理注册、密码验证和登录会话创建。"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.auth import LoginInput, LoginResult, RegisterInput, RegisterResult
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.core.security import hash_password, hash_session_token, verify_password
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
    """校验账号密码并创建一个有过期时间的登录会话。"""
    user = db.scalar(select(User).where(User.account == payload.account))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(code=40101, message="账号或密码错误", status_code=401)

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
        # commit 才会真正写入数据库；失败时必须 rollback 才能恢复会话。
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ApiError(code=40902, message="账号已注册", status_code=409) from error

    # 刷新对象以读取数据库生成的自增 id，再构造不含密码的公开响应。
    db.refresh(user)
    return success(
        RegisterResult(
            user_id=user.id,
            username=user.username,
            account=user.account,
        ).model_dump()
    )
