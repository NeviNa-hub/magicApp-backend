"""文字视频后台进程：python -m app.workers.video_generation。"""

import json
import logging
import time
from datetime import datetime, timezone
from urllib.error import HTTPError

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models.task import GenerationTask
from app.db.models.work import Work
from app.db.session import SessionLocal
from app.services.file_deletions import cleanup_pending_file_deletions
from app.services.siliconflow_video import get_video_status, submit_video
from app.services.tasks import fail_task

logger = logging.getLogger(__name__)


def mark_submission_unknown(task_id: int) -> None:
    """终止无法确认上游结果的任务，保留核查标记，防止重复提交计费。"""
    with SessionLocal() as db:
        task = db.get(GenerationTask, task_id, with_for_update=True)
        if task and task.status == "processing" and not (task.result_data or {}).get("provider_id"):
            task.status = "failed"
            task.error_message = "视频提交结果暂无法确认，请联系管理员核查。"
            task.result_data = {**(task.result_data or {}), "submission_unknown": True}
            db.commit()


# 视频任务处理函数
def run_one() -> bool:
    """领取待提交任务，或继续查询已提交的视频。"""
    with SessionLocal() as db:
        cleanup_pending_file_deletions(db, limit=5)
        # 兼容旧任务，并给仍在提交中的其他 worker 留出网络超时和保存窗口。
        cutoff_seconds = get_settings().siliconflow_timeout_seconds + 60
        stale = db.scalars(
            select(GenerationTask).where(
                GenerationTask.task_type == "video",
                GenerationTask.status == "processing",
                GenerationTask.result_data["provider_id"].as_string().is_(None),
            )
        ).all()
        for item in stale:
            updated = item.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - updated).total_seconds() > cutoff_seconds:
                mark_submission_unknown(item.id)
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
            task_id, user_id, data = task.id, task.user_id, dict(task.input_data)
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
            task_id, user_id, data = task.id, task.user_id, None
            provider_id = task.result_data["provider_id"]
    if data is not None:
        try:
            provider_id = submit_video(data)
            with SessionLocal() as db:
                task = db.get(GenerationTask, task_id, with_for_update=True)
                if task and task.status == "processing":
                    task.result_data = {"provider_id": provider_id}
                    db.commit()
        except HTTPError as error:
            if error.code in {400, 401, 402, 403, 404, 422, 429}:
                logger.error("视频提交被拒绝 task_id=%s http_status=%s", task_id, error.code)
                with SessionLocal() as db:
                    fail_task(db, user_id, task_id, "视频服务拒绝请求，请联系管理员检查配置或额度。", refund=True)
            else:
                mark_submission_unknown(task_id)
            return True
        except Exception:
            mark_submission_unknown(task_id)
            # 提交结果未知时禁止自动重发，防止第三方重复计费。
            logger.exception("视频提交状态未知 task_id=%s，需人工核查", task_id)
            return True
    try:
        result = get_video_status(provider_id)
        status = result.get("status")
        if status == "Failed":
            # 第三方明确失败且未产出视频，按未计费处理并退回本次扣费。
            with SessionLocal() as db:
                fail_task(db, user_id, task_id, "视频生成失败，请稍后重试", refund=True)
            return True
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id, with_for_update=True)
            if not task or task.status != "processing":
                return True
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
            task.updated_at = func.now()
            db.commit()
    except HTTPError as error:
        try:
            body = json.loads(error.read())
        except (ValueError, UnicodeDecodeError):
            body = {}
        if error.code == 404 and isinstance(body, dict) and body.get("code") == 20063:
            # 上游记录已不可查询，结束轮询；计费未知，保留标识供人工核查。
            with SessionLocal() as db:
                task = db.get(GenerationTask, task_id, with_for_update=True)
                if task and task.status == "processing":
                    task.status = "failed"
                    task.error_message = "上游视频任务不存在或已过期，请联系管理员核查生成及计费结果。"
                    task.result_data = {**(task.result_data or {}), "submission_unknown": True}
                    db.commit()
            logger.warning("视频任务上游记录失效 task_id=%s provider_code=20063", task_id)
        else:
            logger.warning("视频状态查询暂不可用 task_id=%s http_status=%s", task_id, error.code)
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
