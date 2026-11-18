"""账号永久注销及本地上传文件清理。"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import verify_password
from app.db.models.account import Account
from app.db.models.asset import Asset
from app.db.models.file_deletion import PendingFileDeletion
from app.db.models.task import GenerationTask
from app.db.models.user import User
from app.services.file_deletions import cleanup_pending_file_deletions
from app.services.uploads import _storage_dir

logger = logging.getLogger(__name__)

# 账号注销服务
def delete_account(db: Session, user_id: int, password: str) -> None:
    """验证本人密码、拒绝进行中任务并永久删除账号数据。"""
    # 与任务创建的账户锁顺序一致，避免注销期间新增扣费任务。
    db.scalar(select(Account).where(Account.user_id == user_id).with_for_update())
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.is_active:
        raise ApiError(message="账号不存在", status_code=404)
    if not verify_password(password, user.password_hash):
        raise ApiError(message="密码错误", status_code=400)
    active_task = db.scalar(
        select(GenerationTask.id)
        .where(
            GenerationTask.user_id == user_id,
            GenerationTask.status.in_(("pending", "processing")),
        )
        .limit(1)
    )
    if active_task is not None:
        raise ApiError(
            message="还有未结束的创作任务，请完成或取消后再注销", status_code=409
        )

    directory = _storage_dir()
    keys = db.scalars(select(Asset.storage_key).where(Asset.user_id == user_id)).all()
    paths = [(directory / key).resolve() for key in keys]
    if any(path.parent != directory for path in paths):
        raise ApiError(message="文件路径异常，无法注销，请联系管理员", status_code=409)

    quarantined = []
    try:
        # 先可逆隔离文件，清理任务与账号删除在同一事务提交。
        for path in paths:
            if not path.exists():
                continue
            quarantine = path.with_name(f".{path.name}.deleting")
            if quarantine.exists():
                raise OSError("账号文件存在未清理的隔离副本")
            path.rename(quarantine)
            quarantined.append(path)
            db.add(PendingFileDeletion(storage_key=path.name))

        # 外键级联删除会话、积分流水、任务、作品与资产记录。
        db.delete(user)
        db.commit()
    except Exception as error:
        db.rollback()
        for path in reversed(quarantined):
            quarantine = path.with_name(f".{path.name}.deleting")
            try:
                if quarantine.exists() and not path.exists():
                    quarantine.rename(path)
                elif quarantine.exists():
                    logger.error(
                        "原文件已存在，保留隔离副本供管理员处理：%s", quarantine
                    )
            except OSError:
                logger.exception("账号注销失败后恢复隔离文件失败：%s", quarantine)
        if isinstance(error, OSError):
            raise ApiError(
                message="文件清理失败，请稍后重试", status_code=500
            ) from error
        raise

    # 先尝试立即清理；失败任务会由已有 worker 继续退避重试。
    try:
        cleanup_pending_file_deletions(
            db,
            limit=max(1, len(quarantined)),
            storage_keys=[path.name for path in quarantined],
        )
    except Exception:
        db.rollback()
        logger.exception("账号注销已完成，文件清理任务将由 worker 重试")
