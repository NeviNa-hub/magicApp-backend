"""提供账号密码安全处理。"""

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """生成密码哈希，只将哈希写入数据库。"""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证用户输入的密码是否匹配数据库中的哈希。"""
    return password_hasher.verify(password, password_hash)
