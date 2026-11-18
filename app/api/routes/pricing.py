"""创作积分报价接口。"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.schemas.pricing import PricingQuoteInput, PricingQuoteResult
from app.core.pricing import quote_task
from app.core.responses import ApiResponse, success
from app.db.models.user import User

router = APIRouter(prefix="/pricing", tags=["积分定价"])

# 获取积分报价接口
@router.post("/quote", response_model=ApiResponse)
def quote_creation(
    payload: PricingQuoteInput,
    _user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    """按任务类型与提示词返回预计 token 和积分，创建任务时复用同一计价函数。"""
    quote = quote_task(
        payload.task_type, payload.prompt, payload.style, payload.duration
    )
    return success(PricingQuoteResult(**quote.as_dict()).model_dump())
