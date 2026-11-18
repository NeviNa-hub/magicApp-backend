"""当前用户的作品库接口。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.library import UpdateWorkCover, UpdateWorkTitle
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.db.session import get_db
from app.services.library import (
    delete_work,
    get_library,
    get_work_media,
    update_video_cover,
    update_work_title,
)

router = APIRouter(prefix="/library", tags=["作品库"])


# 查询作品库接口
@router.get("", response_model=ApiResponse)
def list_library(
    status: Literal["all", "completed", "creating", "canceled", "draft"] = "all",
    keyword: str = Query(default="", max_length=255),
    work_type: Literal["all", "image", "optimization", "video"] = Query(
        default="all", alias="type"
    ),
    sort: Literal["newest", "oldest"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """查询本人作品、进行中的任务和已取消的任务。"""
    result = get_library(db, user.id, status, page, page_size, keyword, work_type, sort)
    return success(result.model_dump(mode="json"))


# 删除作品接口
@router.delete("/works/{work_id}", response_model=ApiResponse)
def remove_work(
    work_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """删除本人作品；作品不存在或不属于本人时返回 404。"""
    delete_work(db, user.id, work_id)
    return success({"work_id": work_id})


# 更新作品标题接口
@router.put("/works/{work_id}", response_model=ApiResponse)
def rename_work(
    work_id: int,
    body: UpdateWorkTitle,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """修改本人已完成作品的标题。"""
    work = update_work_title(db, user.id, work_id, body.title)
    return success({"work_id": work.id, "title": work.title})


# 查询作品媒体接口
@router.get("/works/{work_id}/media", response_model=ApiResponse)
def read_work_media(
    work_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """获取本人作品的原始媒体地址，地址有效期由媒体服务决定。"""
    work = get_work_media(db, user.id, work_id)
    return success(
        {
            "work_id": work.id,
            "media_url": work.media_url,
            "media_type": work.media_type,
            "cover_asset_id": work.cover_asset_id,
        }
    )


# 更新作品封面接口
@router.put("/works/{work_id}/cover", response_model=ApiResponse)
def set_work_cover(
    work_id: int,
    body: UpdateWorkCover,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """设置或移除本人视频作品封面。"""
    work = update_video_cover(db, user.id, work_id, body.cover_asset_id)
    return success({"work_id": work.id, "cover_asset_id": work.cover_asset_id})
