"""MediaMaid 插件框架。

对外暴露基类、注册/发现 API。各类别的内置实现在同名子包中。
"""

from .base import (
    CATEGORIES,
    Downloader,
    EmptyConfig,
    Notifier,
    Parser,
    Plugin,
    Scraper,
    Subscriber,
)
from .registry import available, close_plugins, create, get, load_plugins, register

__all__ = [
    "Plugin",
    "Parser",
    "Scraper",
    "Subscriber",
    "Downloader",
    "Notifier",
    "EmptyConfig",
    "CATEGORIES",
    "register",
    "create",
    "get",
    "available",
    "load_plugins",
    "close_plugins",
]
