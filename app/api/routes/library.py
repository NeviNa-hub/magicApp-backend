"""当前用户的作品库接口。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.db.session import get_db
from app.services.library import get_library

router = APIRouter(prefix="/library", tags=["作品库"])


@router.get("", response_model=ApiResponse)
def list_library(
    status: Literal["all", "completed", "creating", "draft"] = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """查询本人作品和进行中的任务；草稿暂为空。"""
    result = get_library(db, user.id, status, page, page_size)
    return success(result.model_dump(mode="json"))
