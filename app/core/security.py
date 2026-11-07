"""提供账号密码安全处理：保存不可逆哈希，并校验登录密码。"""

import hashlib

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """生成密码哈希，只将哈希写入数据库。"""
    # 使用推荐的 Argon2 参数；不要自行保存或记录原始 password。
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证用户输入的密码是否匹配数据库中的哈希。"""
    return password_hasher.verify(password, password_hash)


def hash_session_token(token: str) -> str:
    """生成会话令牌的 SHA-256 摘要，供数据库保存和后续查询。"""
    # 令牌本身由安全随机数生成，熵足够高，使用快速摘要即可避免保存原始令牌。
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
