"""定义可预期的业务错误。"""

from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    """保存统一错误码、提示文字和 HTTP 状态码。"""

    code: int
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message
