"""图片上传和本人图片访问接口。"""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.db.session import get_db
from app.services.uploads import get_image, save_image

router = APIRouter(prefix="/uploads/images", tags=["图片上传"])


@router.post("", response_model=ApiResponse)
async def upload_image(
    file: UploadFile = File(...),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ApiResponse:
    """上传本人图片；multipart 字段名为 file。"""
    result = await save_image(db, user.id, file)
    return success(result.model_dump())


@router.get("/{upload_id}")
def read_image(
    upload_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> FileResponse:
    """返回本人图片，避免公开用户上传的原图。"""
    asset, path = get_image(db, user.id, upload_id)
    return FileResponse(path, media_type=asset.content_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
