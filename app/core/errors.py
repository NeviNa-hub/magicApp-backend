"""定义可预期的业务错误。"""

from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    """保存提示文字与 HTTP 状态码；响应 code 与状态码保持一致。"""

    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message
