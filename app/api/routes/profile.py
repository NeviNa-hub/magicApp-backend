"""本人资料查询与编辑。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.db.models.asset import Asset
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/profile", tags=["个人资料"])


class ProfileInput(BaseModel):
    """编辑昵称和本人上传的头像标识。"""

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    avatar_asset_id: int | None = None


def _profile(user: User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "account": user.account,
        "avatar_asset_id": user.avatar_asset_id,
    }


@router.get("", response_model=ApiResponse)
def read_profile(user: User = Depends(get_current_user)) -> ApiResponse:  # noqa: B008
    """读取当前用户资料。"""
    return success(_profile(user))


@router.put("", response_model=ApiResponse)
def update_profile(
    body: ProfileInput,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """修改本人资料；头像必须是本人上传的资产。"""
    if body.avatar_asset_id is not None:
        asset = db.scalar(
            select(Asset).where(Asset.id == body.avatar_asset_id, Asset.user_id == user.id)
        )
        if asset is None:
            raise ApiError(message="头像不存在", status_code=404)
    user.username = body.username
    user.avatar_asset_id = body.avatar_asset_id
    db.add(user)
    db.commit()
    db.refresh(user)
    return success(_profile(user))
