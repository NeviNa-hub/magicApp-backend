"""创作草稿接口。"""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/drafts", tags=["创作草稿"])


class DraftInput(BaseModel):
    """保存尚未提交的创作参数。"""

    task_type: Literal["image", "optimization", "video"]
    title: str = Field(min_length=1, max_length=50)
    input_data: dict


def _get_draft(db: Session, user_id: int, task_id: str) -> GenerationTask:
    """只允许操作属于当前用户且仍可编辑的草稿。"""
    draft = db.scalar(
        select(GenerationTask)
        .where(
            GenerationTask.user_id == user_id,
            GenerationTask.task_id == task_id,
            GenerationTask.status == "draft",
        )
        .with_for_update()
    )
    if draft is None:
        raise ApiError(message="草稿不存在或已提交", status_code=404)
    return draft


def _serialize(draft: GenerationTask) -> dict:
    return {
        "id": draft.task_id,
        "title": draft.title,
        "task_type": draft.task_type,
        "input_data": draft.input_data,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


# 创建草稿接口
@router.post("", response_model=ApiResponse)
def create_draft(
    body: DraftInput,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """创建本人未提交的编辑草稿。"""
    title = body.title.strip()
    if not title or not body.input_data:
        raise ApiError(message="请填写草稿内容", status_code=400)
    draft = GenerationTask(
        task_id=uuid4().hex,
        user_id=user.id,
        task_type=body.task_type,
        title=title,
        input_data=body.input_data,
        status="draft",
        cost_points=0,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return success(_serialize(draft))


# 查询草稿接口
@router.get("", response_model=ApiResponse)
def list_drafts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """按更新时间分页查询本人草稿。"""
    condition = (GenerationTask.user_id == user.id, GenerationTask.status == "draft")
    total = (
        db.scalar(select(func.count()).select_from(GenerationTask).where(*condition))
        or 0
    )
    items = db.scalars(
        select(GenerationTask)
        .where(*condition)
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return success(
        {
            "items": [_serialize(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# 查询草稿详情接口
@router.get("/{draft_id}", response_model=ApiResponse)
def read_draft(
    draft_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """查询本人仍可编辑的草稿。"""
    return success(_serialize(_get_draft(db, user.id, draft_id)))


# 更新草稿接口
@router.put("/{draft_id}", response_model=ApiResponse)
def update_draft(
    draft_id: str,
    body: DraftInput,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """更新本人草稿的标题和参数。"""
    draft = _get_draft(db, user.id, draft_id)
    if (
        draft.task_type != body.task_type
        or not body.title.strip()
        or not body.input_data
    ):
        raise ApiError(message="草稿内容无效", status_code=400)
    draft.title = body.title.strip()
    draft.input_data = body.input_data
    db.commit()
    db.refresh(draft)
    return success(_serialize(draft))


# 删除草稿接口
@router.delete("/{draft_id}", response_model=ApiResponse)
def delete_draft(
    draft_id: str,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """删除本人未提交的草稿。"""
    draft = _get_draft(db, user.id, draft_id)
    db.delete(draft)
    db.commit()
    return success({"id": draft_id})
