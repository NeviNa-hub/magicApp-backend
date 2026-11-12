"""作品库查询服务。"""

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from app.api.schemas.library import LibraryItem, LibraryPageInfo, LibraryResult, LibraryTab
from app.db.models.task import GenerationTask
from app.db.models.work import Work

TYPE_NAMES = {"image": "文字生图", "optimization": "图片优化", "video": "视频创作"}


def get_library(db: Session, user_id: int, status: str, page: int, page_size: int) -> LibraryResult:
    """合并本人进行中任务与已完成作品，按时间和类型、主键稳定排序。"""
    completed_count = db.scalar(
        select(func.count()).select_from(Work).where(
            Work.user_id == user_id, Work.status == "completed"
        )
    ) or 0
    creating_count = db.scalar(
        select(func.count()).select_from(GenerationTask).where(
            GenerationTask.user_id == user_id,
            GenerationTask.status.in_(("pending", "processing")),
        )
    ) or 0
    tabs = [
        LibraryTab(status="all", name="全部", count=completed_count + creating_count),
        LibraryTab(status="completed", name="已完成", count=completed_count),
        LibraryTab(status="creating", name="创作中", count=creating_count),
        # 尚无草稿存储模型，不把等待中的任务当作草稿。
        LibraryTab(status="draft", name="草稿", count=0),
    ]
    total = {tab.status: tab.count for tab in tabs}[status]
    items = []
    if total:
        works = select(
            Work.id.label("id"), Work.created_at.label("created_at"), literal("work").label("kind")
        ).where(Work.user_id == user_id, Work.status == "completed")
        tasks = select(
            GenerationTask.id.label("id"),
            GenerationTask.created_at.label("created_at"),
            literal("task").label("kind"),
        ).where(
            GenerationTask.user_id == user_id,
            GenerationTask.status.in_(("pending", "processing")),
        )
        query = union_all(works, tasks).subquery() if status == "all" else (
            works.subquery() if status == "completed" else tasks.subquery()
        )
        rows = db.execute(
            select(query).order_by(query.c.created_at.desc(), query.c.kind, query.c.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        work_ids = [row.id for row in rows if row.kind == "work"]
        task_ids = [row.id for row in rows if row.kind == "task"]
        work_rows = db.execute(
            select(Work, GenerationTask).outerjoin(
                GenerationTask,
                (Work.task_id == GenerationTask.id) & (GenerationTask.user_id == user_id),
            ).where(Work.user_id == user_id, Work.id.in_(work_ids))
        ).all() if work_ids else []
        works_by_id = {work.id: (work, task) for work, task in work_rows}
        tasks_by_id = {
            task.id: task for task in db.scalars(
                select(GenerationTask).where(
                    GenerationTask.user_id == user_id, GenerationTask.id.in_(task_ids)
                )
            ).all()
        } if task_ids else {}
        for row in rows:
            if row.kind == "work" and row.id in works_by_id:
                work, task = works_by_id[row.id]
                items.append(LibraryItem(
                    work_id=work.id, task_id=task.task_id if task else None, title=work.title,
                    status="completed", type_name=TYPE_NAMES.get(task.task_type, "作品") if task else "作品",
                    created_at=work.created_at, media_url=work.media_url,
                ))
            elif row.kind == "task" and row.id in tasks_by_id:
                task = tasks_by_id[row.id]
                prompt = task.input_data.get("prompt") if isinstance(task.input_data, dict) else None
                items.append(LibraryItem(
                    work_id=-task.id, task_id=task.task_id,
                    title=str(prompt)[:255] if prompt else "未命名任务", status="creating",
                    type_name=TYPE_NAMES.get(task.task_type, "创作任务"),
                    created_at=task.created_at, media_url=None,
                ))
    return LibraryResult(
        tabs=tabs, page_info=LibraryPageInfo(page=page, page_size=page_size, total=total), lists=items
    )
