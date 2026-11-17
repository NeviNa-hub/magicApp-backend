"""生成任务与作品共用的状态枚举。

数据库端由迁移 0006 添加 CHECK 约束；新增状态时必须同时新增迁移，
否则写入会被数据库拒绝。
"""

from enum import Enum


class GenerationStatus(str, Enum):
    """生成流程的有限状态集合。"""

    draft = "draft"
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


# 任务允许编辑草稿；作品状态仍遵循原有状态集合。
STATUS_CHECK_SQL = (
    "status IN (" + ", ".join(f"'{s.value}'" for s in GenerationStatus) + ")"
)
WORK_STATUS_CHECK_SQL = (
    "status IN ("
    + ", ".join(f"'{s.value}'" for s in GenerationStatus if s != GenerationStatus.draft)
    + ")"
)
