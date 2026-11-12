"""数据库驱动的文字生图后台进程：python -m app.workers.image_generation。"""

import logging
import time

from sqlalchemy import select

from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import SessionLocal
from app.services.siliconflow import generate_image
from app.services.siliconflow_image_edit import optimize_image
from app.services.uploads import get_image

logger = logging.getLogger(__name__)


def run_one() -> bool:
    """原子领取任务；失败记录为终态，不自动重复调用第三方。"""
    # 行锁和 SKIP LOCKED 让多个进程不会同时领取同一个等待任务。
    with SessionLocal() as db:
        task = db.scalar(
            select(GenerationTask)
            .where(
                GenerationTask.task_type.in_(("image", "optimization")),
                GenerationTask.status == "pending",
            )
            .order_by(GenerationTask.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return False
        task.status = "processing"
        task_id, user_id, data = task.id, task.user_id, dict(task.input_data)
        task_type = task.task_type
        db.commit()
    try:
        # 先提交领取状态，再调用外部服务，避免持有数据库锁等待网络。
        if task_type == "optimization":
            # 原图是私有文件，后端校验归属后以 Base64 发送，不暴露受保护地址。
            with SessionLocal() as db:
                asset, path = get_image(db, user_id, int(data["upload_id"]))
                image_bytes, content_type = path.read_bytes(), asset.content_type
            url = optimize_image(image_bytes, content_type, data["prompt"])
        else:
            url = generate_image(data)
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id, with_for_update=True)
            if task is None or task.status != "processing":
                return True
            # 作品和完成状态一起提交，避免完成后作品尚未写入。
            db.add(
                Work(
                    user_id=user_id,
                    task_id=task.id,
                    title=data["prompt"][:255],
                    status="completed",
                    media_url=url,
                    media_type="image",
                )
            )
            task.result_data = {"result_urls": [url]}
            task.progress = 100
            task.status = "completed"
            db.commit()
    # 不自动重试第三方调用，避免结果不明确时重复生成及计费。
    except Exception:
        logger.exception("图片任务处理失败 task_id=%s", task_id)
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id, with_for_update=True)
            if task and task.status == "processing":
                task.status = "failed"
                task.error_message = "图片生成失败，请稍后重试"
                db.commit()
    return True


def main() -> None:
    """持续领取任务。"""
    while True:
        try:
            if not run_one():
                time.sleep(3)
        except Exception:
            logger.exception("任务轮询失败")
            time.sleep(5)


if __name__ == "__main__":
    main()
