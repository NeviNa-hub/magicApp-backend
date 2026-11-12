"""文字视频后台进程：python -m app.workers.video_generation。"""

import logging
import time

from sqlalchemy import func, select

from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import SessionLocal
from app.services.siliconflow_video import get_video_status, submit_video

logger = logging.getLogger(__name__)


def run_one() -> bool:
    """领取待提交任务，或继续查询已提交的视频。"""
    with SessionLocal() as db:
        task = db.scalar(
            select(GenerationTask)
            .where(
                GenerationTask.task_type == "video", GenerationTask.status == "pending"
            )
            .order_by(GenerationTask.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task:
            task.status = "processing"
            task_id, data = task.id, dict(task.input_data)
            db.commit()
        else:
            task = db.scalar(
                select(GenerationTask)
                .where(
                    GenerationTask.task_type == "video",
                    GenerationTask.status == "processing",
                    GenerationTask.result_data["provider_id"].as_string().is_not(None),
                )
                .order_by(GenerationTask.updated_at, GenerationTask.id)
                .limit(1)
            )
            if (
                not task
                or not isinstance(task.result_data, dict)
                or not task.result_data.get("provider_id")
            ):
                return False
            task_id, data = task.id, None
            provider_id = task.result_data["provider_id"]
    if data is not None:
        try:
            provider_id = submit_video(data)
            with SessionLocal() as db:
                task = db.get(GenerationTask, task_id, with_for_update=True)
                if task and task.status == "processing":
                    task.result_data = {"provider_id": provider_id}
                    db.commit()
        except Exception:
            # 提交结果未知时禁止自动重发，防止第三方重复计费。
            logger.exception("视频提交状态未知 task_id=%s，需人工核查", task_id)
            return True
    try:
        result = get_video_status(provider_id)
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id, with_for_update=True)
            if not task or task.status != "processing":
                return True
            status = result.get("status")
            if status == "Succeed":
                videos = (result.get("results") or {}).get("videos") or []
                url = (
                    videos[0].get("url")
                    if videos and isinstance(videos[0], dict)
                    else None
                )
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("视频结果地址无效")
                db.add(
                    Work(
                        user_id=task.user_id,
                        task_id=task.id,
                        title=task.input_data["prompt"][:255],
                        status="completed",
                        media_url=url,
                        media_type="video",
                    )
                )
                task.result_data = {"provider_id": provider_id, "result_urls": [url]}
                task.status, task.progress = "completed", 100
            elif status == "Failed":
                task.status = "failed"
                task.error_message = "视频生成失败，请稍后重试"
            task.updated_at = func.now()
            db.commit()
    except Exception:
        # 查询失败不代表任务失败，下次继续使用已保存的 requestId 查询。
        logger.exception("视频状态查询失败 task_id=%s", task_id)
    return True


def main() -> None:
    while True:
        try:
            run_one()
        except Exception:
            logger.exception("视频任务轮询失败")
        time.sleep(10)


if __name__ == "__main__":
    main()
