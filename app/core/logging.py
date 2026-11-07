"""配置不包含敏感请求内容的应用日志。"""

import logging

from app.core.config import get_settings


def setup_logging() -> None:
    """设置简洁日志格式，不记录请求正文或凭据。"""
    settings = get_settings()
    logging.basicConfig(
        level=settings.app_log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
