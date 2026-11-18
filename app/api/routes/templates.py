"""内置创作模板及其可编辑参数。"""

from typing import Literal

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.responses import ApiResponse, success
from app.db.models.user import User

router = APIRouter(prefix="/templates", tags=["创作模板"])

# 模板是可修改的创作起点，不代表已经生成的作品。
TEMPLATES = (
    {
        "id": "image-mountains",
        "title": "晨雾山水",
        "type": "image",
        "description": "青绿山水与晨雾",
        "params": {
            "prompt": "晨雾缭绕的山水，远山层叠，溪边一叶小舟，画面宁静通透",
            "style": "古风水墨",
            "ratio": "16:9",
        },
    },
    {
        "id": "image-cat",
        "title": "午后小猫",
        "type": "image",
        "description": "温暖治愈的生活场景",
        "params": {
            "prompt": "阳光洒在窗边，一只橘猫安静地睡在软垫上，温暖柔和",
            "style": "真实摄影",
            "ratio": "1:1",
        },
    },
    {
        "id": "video-river",
        "title": "溪流远山",
        "type": "video",
        "description": "缓慢移动的自然镜头",
        "params": {
            "prompt": "清晨山间溪水缓缓流动，薄雾掠过远山，镜头平稳向前推进",
            "mode": "text",
            "ratio": "16:9",
        },
    },
    {
        "id": "video-rain",
        "title": "雨后街景",
        "type": "video",
        "description": "细雨与街道光影",
        "params": {
            "prompt": "雨后街道映着柔和灯光，行人撑伞缓缓走过，镜头轻轻移动",
            "mode": "text",
            "ratio": "9:16",
        },
    },
)


# 查询模板接口
@router.get("", response_model=ApiResponse)
def list_templates(
    type: Literal["all", "image", "video"] = "all",
    user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    """查询内置模板，可按创作类型筛选。"""
    return success(
        {"items": [item for item in TEMPLATES if type == "all" or item["type"] == type]}
    )
