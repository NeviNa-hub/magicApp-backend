"""重试账号注销后残留的本地文件清理。"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.file_deletion import PendingFileDeletion
from app.services.uploads import _storage_dir

logger = logging.getLogger(__name__)  # 日志记录器

# 文件清理服务
def cleanup_pending_file_deletions(
    db: Session, limit: int = 20, storage_keys: list[str] | None = None
) -> int:
    """删除到期文件并清除任务；失败时采用退避间隔重试。"""
    statement = (
        select(PendingFileDeletion)
        .where(PendingFileDeletion.next_attempt_at <= func.now())
        .order_by(PendingFileDeletion.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    if storage_keys is not None:
        if not storage_keys:
            return 0
        statement = statement.where(PendingFileDeletion.storage_key.in_(storage_keys))

    pending = db.scalars(statement).all()
    if not pending:
        return 0

    directory = _storage_dir()
    cleaned = 0
    for item in pending:
        try:
            original = (directory / item.storage_key).resolve()
            quarantine = (directory / f".{original.name}.deleting").resolve()
            if original.parent != directory or quarantine.parent != directory:
                raise ValueError("文件路径超出受控目录")
            original.unlink(missing_ok=True)
            quarantine.unlink(missing_ok=True)
            db.delete(item)
            cleaned += 1
        except (OSError, RuntimeError, ValueError):
            item.attempts += 1
            delay_seconds = min(5 * (2 ** min(item.attempts - 1, 10)), 3600)
            item.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                seconds=delay_seconds
            )
            logger.exception(
                "注销文件清理失败，稍后重试 storage_key=%s", item.storage_key
            )

    db.commit()
    return cleaned
