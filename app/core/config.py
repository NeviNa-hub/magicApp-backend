"""读取开发或服务器环境配置；敏感配置由环境变量或未提交的 .env 提供。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务运行配置；密码等私密值只放在不提交的 .env 文件中。"""

    app_env: str = "development"
    app_log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://magicapp:local_dev_password@127.0.0.1:5432/magicapp_db"
    )
    database_connect_timeout: int = 3
    session_expire_days: int = Field(default=7, ge=1, le=90)
    # 允许跨域的前端来源，逗号分隔；只填协议+域名+端口，末尾不要带斜杠。
    cors_allow_origins: str = "http://localhost:5173"

    # 环境变量优先于 .env；extra=ignore 允许部署环境存在其他无关变量。
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        """把逗号分隔的配置解析成来源列表，忽略空项。"""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """读取并缓存服务配置。"""
    # 配置在进程内通常固定，缓存可避免重复解析配置文件。
    return Settings()
