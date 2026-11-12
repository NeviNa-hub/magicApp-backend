"""上传图片的校验、持久化和归属查询。"""

import os
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.uploads import UploadedImageResult
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models.asset import Asset

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
CHUNK_SIZE = 64 * 1024
FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


def _storage_dir() -> Path:
    """解析受控存储目录；文件名由服务端生成，不使用客户端路径。"""
    return Path(get_settings().upload_dir).expanduser().resolve()


def _safe_name(filename: str | None) -> str:
    """仅保留文件名，去除路径及控制字符，限制数据库字段长度。"""
    name = (filename or "image").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:255] or "image"


async def save_image(
    db: Session, user_id: int, file: UploadFile
) -> UploadedImageResult:
    """限制文件大小，校验图片内容并写入文件及资产记录。"""
    directory = _storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    # 随机文件名避免路径穿越与不同用户文件名碰撞。
    temp_path = directory / (uuid4().hex + ".tmp")
    final_path = None
    try:
        size = 0
        with temp_path.open("xb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ApiError(
                        code=41301, message="图片不能超过 5 MB", status_code=413
                    )
                destination.write(chunk)
        if not size:
            raise ApiError(code=40001, message="图片文件不能为空", status_code=400)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(temp_path) as image:
                    image_format = image.format
                    if image_format not in FORMATS:
                        raise ApiError(
                            code=40002,
                            message="仅支持 JPEG、PNG、WebP 图片",
                            status_code=400,
                        )
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ApiError(
                            code=40002, message="图片尺寸过大", status_code=400
                        )
                    image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise ApiError(
                code=40002, message="图片文件无效或尺寸过大", status_code=400
            ) from error

        content_type, suffix = FORMATS[image_format]
        storage_key = uuid4().hex + suffix
        final_path = directory / storage_key
        os.replace(temp_path, final_path)
        asset = Asset(
            user_id=user_id,
            storage_key=storage_key,
            public_url="",
            original_name=_safe_name(file.filename),
            content_type=content_type,
            size_bytes=size,
        )
        db.add(asset)
        db.flush()
        # 该路径需要鉴权，前端请求时需携带登录令牌。
        asset.public_url = f"/api/uploads/images/{asset.id}"
        db.commit()
        return UploadedImageResult(
            upload_id=str(asset.id), url=asset.public_url, name=asset.original_name
        )
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def get_image(db: Session, user_id: int, upload_id: int) -> tuple[Asset, Path]:
    """仅允许资产所属用户读取，其他用户与不存在统一返回 404。"""
    asset = db.scalar(
        select(Asset).where(Asset.id == upload_id, Asset.user_id == user_id)
    )
    if asset is None:
        raise ApiError(code=40403, message="图片不存在", status_code=404)
    directory = _storage_dir()
    path = (directory / asset.storage_key).resolve()
    if path.parent != directory or not path.is_file():
        raise ApiError(code=40403, message="图片不存在", status_code=404)
    return asset, path
