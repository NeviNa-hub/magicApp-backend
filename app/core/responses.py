"""定义前后端共用的接口响应格式。"""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一接口返回的状态码、提示和数据字段。"""

    code: int = 0
    message: str = "操作成功"
    data: Any = None


def success(data: Any = None, message: str = "操作成功") -> ApiResponse:
    """构造成功响应。"""
    return ApiResponse(data=data, message=message)
