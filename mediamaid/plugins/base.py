"""插件基类与四大类别抽象接口。

新增一个插件 = 在 plugins/<category>/ 下放一个模块，定义 Plugin 子类并 @register。
重依赖请在 __init__ / 方法内惰性 import，避免 load_plugins() 因缺依赖整体失败。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Type

from pydantic import BaseModel

from ..models import Event, MediaInfo, MediaItem, Release


class EmptyConfig(BaseModel):
    """无需配置的插件的默认配置模型。"""

    model_config = {"extra": "ignore"}


class Plugin(ABC):
    """所有插件的基类。

    子类需声明类属性 category / name，并可声明 ConfigModel。
    """

    category: str = ""
    name: str = ""
    ConfigModel: Type[BaseModel] = EmptyConfig

    def __init__(self, config: BaseModel):
        self.config = config

    def __repr__(self) -> str:  # pragma: no cover - 便于调试
        return f"<{self.category}:{self.name}>"


class Scraper(Plugin):
    """刮削器：根据识别结果查询权威元数据。"""

    category = "scraper"

    @abstractmethod
    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        raise NotImplementedError


class Subscriber(Plugin):
    """订阅器：从 RSS/站点发现新资源。"""

    category = "subscriber"

    @abstractmethod
    def fetch(self) -> List[Release]:
        raise NotImplementedError


class Downloader(Plugin):
    """下载器：把 Release 投递给下载客户端。"""

    category = "downloader"

    @abstractmethod
    def add(self, release: Release) -> bool:
        """提交下载，成功返回 True。"""
        raise NotImplementedError

    def list_completed(self) -> List[Path]:
        """返回已完成任务的文件/目录路径（可选，便于闭环）。"""
        return []


class Notifier(Plugin):
    """通知器：推送事件。"""

    category = "notifier"

    @abstractmethod
    def notify(self, event: Event) -> None:
        raise NotImplementedError


# 类别名 -> 基类，供 registry 校验插件归属
CATEGORIES = {
    Scraper.category: Scraper,
    Subscriber.category: Subscriber,
    Downloader.category: Downloader,
    Notifier.category: Notifier,
}
