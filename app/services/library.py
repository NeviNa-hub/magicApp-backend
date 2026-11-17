"""作品库查询服务。"""

from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Subquery

from app.api.schemas.library import (
    LibraryItem,
    LibraryPageInfo,
    LibraryResult,
    LibraryTab,
)
from app.core.errors import ApiError
from app.db.models.task import GenerationTask
from app.db.models.work import Work

TYPE_NAMES = {"image": "文字生图", "optimization": "图片优化", "video": "视频创作"}
CREATING_STATUSES = ("pending", "processing")
# 用户取消的任务保留在草稿中，避免记录直接从作品库消失。
DRAFT_STATUSES = ("canceled",)


def get_library(
    db: Session,
    user_id: int,
    status: str,
    page: int,
    page_size: int,
    keyword: str = "",
    work_type: str = "all",
    sort: str = "newest",
) -> LibraryResult:
    """查询本人创作中任务、草稿与已完成作品，返回各状态数量和当前页。"""
    completed_count = (
        db.scalar(
            select(func.count())
            .select_from(Work)
            .where(Work.user_id == user_id, Work.status == "completed")
        )
        or 0
    )
    creating_count = (
        db.scalar(
            select(func.count())
            .select_from(GenerationTask)
            .where(
                GenerationTask.user_id == user_id,
                GenerationTask.status.in_(CREATING_STATUSES),
            )
        )
        or 0
    )
    draft_count = (
        db.scalar(
            select(func.count())
            .select_from(GenerationTask)
            .where(
                GenerationTask.user_id == user_id,
                GenerationTask.status.in_(DRAFT_STATUSES),
            )
        )
        or 0
    )
    tabs = [
        LibraryTab(
            status="all",
            name="全部",
            count=completed_count + creating_count + draft_count,
        ),
        LibraryTab(status="completed", name="已完成", count=completed_count),
        LibraryTab(status="creating", name="创作中", count=creating_count),
        # 已取消的任务作为草稿保留，用户可在作品库继续查看。
        LibraryTab(status="draft", name="草稿", count=draft_count),
    ]
    # 标签数量保持全局状态统计；分页总数按搜索、类型及状态筛选。
    query = _build_filtered_query(user_id, status, keyword.strip(), work_type)
    total = db.scalar(select(func.count()).select_from(query)) or 0
    items = _get_page_items(db, user_id, status, page, page_size, query, sort) if total else []
    return LibraryResult(
        tabs=tabs,
        page_info=LibraryPageInfo(page=page, page_size=page_size, total=total),
        lists=items,
    )


def _build_filtered_query(user_id: int, status: str, keyword: str, work_type: str) -> Subquery:
    """在合并与分页前筛选本人作品和任务。"""
    works = (
        select(
            Work.id.label("id"), Work.created_at.label("created_at"), literal("work").label("kind")
        )
        .outerjoin(
            GenerationTask,
            (Work.task_id == GenerationTask.id) & (GenerationTask.user_id == user_id),
        )
        .where(Work.user_id == user_id, Work.status == "completed")
    )
    tasks = select(
        GenerationTask.id.label("id"),
        GenerationTask.created_at.label("created_at"),
        literal("task").label("kind"),
    ).where(GenerationTask.user_id == user_id)
    # 无关联任务的历史作品仍可按标题搜索；类型筛选依赖来源任务。
    if work_type != "all":
        works = works.where(GenerationTask.task_type == work_type)
        tasks = tasks.where(GenerationTask.task_type == work_type)
    if keyword:
        # autoescape 将用户输入中的百分号、下划线视为普通字符。
        prompt = GenerationTask.input_data["prompt"].as_string()
        works = works.where(
            or_(
                Work.title.icontains(keyword, autoescape=True),
                prompt.icontains(keyword, autoescape=True),
            )
        )
        tasks = tasks.where(prompt.icontains(keyword, autoescape=True))
    creating = tasks.where(GenerationTask.status.in_(CREATING_STATUSES))
    drafts = tasks.where(GenerationTask.status.in_(DRAFT_STATUSES))
    if status == "all":
        return union_all(works, creating, drafts).subquery()
    if status == "completed":
        return works.subquery()
    return (drafts if status == "draft" else creating).subquery()


def _get_page_items(
    db: Session, user_id: int, status: str, page: int, page_size: int, query: Subquery, sort: str
) -> list[LibraryItem]:
    """先合并并分页，再按当前页的标识批量读取详情。"""
    # 相同创建时间时再按类型和主键排序，避免分页顺序不稳定。
    rows = db.execute(
        select(query)
        .order_by(
            query.c.created_at.asc() if sort == "oldest" else query.c.created_at.desc(),
            query.c.kind,
            query.c.id.asc() if sort == "oldest" else query.c.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    work_ids = [row.id for row in rows if row.kind == "work"]
    task_ids = [row.id for row in rows if row.kind == "task"]

    # 回查仍校验所属用户及状态，防止两次查询期间任务状态变化造成错误展示。
    work_rows = (
        db.execute(
            select(Work, GenerationTask)
            .outerjoin(
                GenerationTask,
                (Work.task_id == GenerationTask.id) & (GenerationTask.user_id == user_id),
            )
            .where(
                Work.user_id == user_id,
                Work.status == "completed",
                Work.id.in_(work_ids),
            )
        ).all()
        if work_ids
        else []
    )
    works_by_id = {work.id: (work, task) for work, task in work_rows}
    # 全部列表同时回查创作中与草稿，避免两次查询之间状态变化导致漏展示。
    if status == "draft":
        task_statuses = DRAFT_STATUSES
    elif status == "creating":
        task_statuses = CREATING_STATUSES
    else:
        task_statuses = CREATING_STATUSES + DRAFT_STATUSES
    tasks_by_id = (
        {
            task.id: task
            for task in db.scalars(
                select(GenerationTask).where(
                    GenerationTask.user_id == user_id,
                    GenerationTask.status.in_(task_statuses),
                    GenerationTask.id.in_(task_ids),
                )
            ).all()
        }
        if task_ids
        else {}
    )
    items = []
    for row in rows:
        if row.kind == "work" and row.id in works_by_id:
            work, task = works_by_id[row.id]
            items.append(
                LibraryItem(
                    work_id=work.id,
                    task_id=task.task_id if task else None,
                    title=work.title,
                    status="completed",
                    type_name=(TYPE_NAMES.get(task.task_type, "作品") if task else "作品"),
                    created_at=work.created_at,
                    media_url=work.media_url,
                )
            )
        elif row.kind == "task" and row.id in tasks_by_id:
            task = tasks_by_id[row.id]
            prompt = task.input_data.get("prompt") if isinstance(task.input_data, dict) else None
            items.append(
                LibraryItem(
                    # 任务主键取负数，避免与作品主键冲突；它不是可访问的作品 ID。
                    work_id=-task.id,
                    task_id=task.task_id,
                    title=str(prompt)[:255] if prompt else "未命名任务",
                    status=("creating" if task.status in CREATING_STATUSES else "draft"),
                    type_name=TYPE_NAMES.get(task.task_type, "创作任务"),
                    created_at=task.created_at,
                    media_url=None,
                )
            )
    return items


def delete_work(db: Session, user_id: int, work_id: int) -> None:
    """删除本人作品；不存在或不属于本人时统一按不存在处理，避免暴露他人数据。"""
    work = db.scalar(select(Work).where(Work.id == work_id, Work.user_id == user_id))
    if work is None:
        raise ApiError(message="作品不存在", status_code=404)
    # 只删除作品记录，来源任务与积分流水保留，便于追溯创作历史。
    db.delete(work)
    db.commit()


def update_work_title(db: Session, user_id: int, work_id: int, title: str) -> Work:
    """修改本人已完成作品的标题，不暴露其他用户的作品。"""
    work = db.scalar(
        select(Work).where(Work.id == work_id, Work.user_id == user_id, Work.status == "completed")
    )
    if work is None:
        raise ApiError(message="作品不存在", status_code=404)
    work.title = title
    db.commit()
    db.refresh(work)
    return work
