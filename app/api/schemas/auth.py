"""注册接口的数据格式：分别校验用户名、登录账号和密码。"""

from datetime import datetime

from pydantic import BaseModel, Field


# 注册接口数据格式
class RegisterInput(BaseModel):
    """注册接口接收的用户名、登录账号和密码。"""

    # Field 设置字段校验；用户名校验前会去掉首尾空格。
    username: str = Field(min_length=1, max_length=64, strip_whitespace=True)
    account: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class RegisterResult(BaseModel):
    """注册成功后返回的公开用户信息，不包含密码或密码哈希。"""

    user_id: int
    username: str
    account: str

# 登录接口数据格式
class LoginInput(BaseModel):
    """登录接口接收的登录账号和密码。"""

    account: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginResult(BaseModel):
    """登录成功后返回的会话令牌和用户资料。"""

    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    user_id: int
    username: str
    account: str
