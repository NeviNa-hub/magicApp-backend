"""注册接口的数据格式：分别校验用户名、登录账号和密码。"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class RegisterInput(BaseModel):
    """注册接口接收的用户名、登录账号和密码。"""
    # Field 和 StringConstraints 都能给字段加校验规则，只是表达方式不同
    # 用户名附加的校验规则：确保用户名长度在 1–64 个字符之间，且不包含空格。
    # 两种方式都可以
    # username: Annotated[
    #     str,
    #     StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    # ]
    username: str = Field(min_length=1, max_length=64, strip_whitespace=True)
    account: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class RegisterResult(BaseModel):
    """注册成功后返回的公开用户信息，不包含密码或密码哈希。"""

    user_id: int
    username: str
    account: str
