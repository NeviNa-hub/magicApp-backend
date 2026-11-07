"""账号注册接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.auth import RegisterInput, RegisterResult
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.core.security import hash_password
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["账号"])


@router.post("/register", response_model=ApiResponse)
def register_user(
    payload: RegisterInput,
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """创建新账号，并以哈希形式保存密码。"""
    existing_user = db.scalar(select(User).where(User.username == payload.username))
    if existing_user:
        raise ApiError(code=40902, message="账号已注册", status_code=409)

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ApiError(code=40902, message="账号已注册", status_code=409) from error

    db.refresh(user)
    return success(RegisterResult(user_id=user.id, username=user.username).model_dump())
