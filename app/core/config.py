"""读取开发或服务器环境中的服务配置。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务运行配置；密码等私密值只放在不提交的 .env 文件中。"""

    app_env: str = "development"
    # 服务默认只监听本机，由 Nginx 等反向代理对外提供 HTTPS。
    app_host: str = "127.0.0.1"
    app_port: int = 8001
    app_log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://magicapp:local_dev_password@127.0.0.1:5432/magicapp"
    database_connect_timeout: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """读取并缓存服务配置。"""
    return Settings()
