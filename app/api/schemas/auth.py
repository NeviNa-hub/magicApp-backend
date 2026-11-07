"""注册和登录接口使用的数据格式。"""

from pydantic import BaseModel, Field


class RegisterInput(BaseModel):
    """注册接口接收的账号和密码。"""

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class RegisterResult(BaseModel):
    """注册成功后返回的公开账号信息。"""

    user_id: int
    username: str
