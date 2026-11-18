"""提示词优化接口。"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.responses import ApiResponse, success
from app.db.models.user import User
from app.services.prompt_optimization import optimize_prompt

router = APIRouter(prefix="/prompts", tags=["提示词"])
LIMITS = {"image": 400, "optimization": 200, "video": 1000}


# 提示词优化输入模型
@router.model_validate()
class PromptInput(BaseModel):
    """创作类型和待优化文本。"""

    task_type: Literal["image", "optimization", "video"]
    prompt: str = Field(min_length=1, max_length=800)

    @field_validator("prompt", mode="before")
    @classmethod
    def trim_prompt(cls, value: object) -> object:
        """去除输入首尾空白。"""
        return value.strip() if isinstance(value, str) else value


# 提示词优化接口
@router.post("/optimize", response_model=ApiResponse)
def optimize(
    body: PromptInput,
    _user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    """认证后优化提示词；仅返回候选文本，不创建任务或扣积分。"""
    limit = LIMITS[body.task_type]
    if len(body.prompt) > limit:
        raise ApiError(message=f"提示词不能超过 {limit} 字", status_code=400)
    settings = get_settings()
    if (
        not settings.siliconflow_api_key.strip()
        or not settings.siliconflow_text_model.strip()
    ):
        raise ApiError(message="提示词优化服务尚未配置", status_code=503)
    try:
        result = optimize_prompt(body.prompt, body.task_type, limit)
    except Exception as error:
        # 不将第三方响应或用户输入写入日志与错误提示。
        raise ApiError(
            message="提示词优化暂不可用，请稍后重试", status_code=502
        ) from error
    if not result or len(result) > limit:
        raise ApiError(message="优化结果无效或过长，请重试", status_code=502)
    return success({"prompt": result})
