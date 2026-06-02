"""插件基类与四大类别抽象接口。

新增一个插件 = 在 plugins/<category>/ 下放一个模块，定义 Plugin 子类并 @register。
重依赖请在 __init__ / 方法内惰性 import，避免 load_plugins() 因缺依赖整体失败。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple, Type

from pydantic import BaseModel

from ..models import DownloadTask, Event, MediaInfo, MediaItem, ParseResult, Release


class EmptyConfig(BaseModel):
    """无需配置的插件的默认配置模型。"""

    model_config = {"extra": "ignore"}


class Plugin(ABC):
    """所有插件的基类。

    子类需声明类属性 category / name，并可声明 ConfigModel。
    description 为一句话用途说明（展示在 Web 插件页）；hidden=True 的插件
    属内部用途（如兜底实现），不在 Web 插件页展示。
    """

    category: str = ""
    name: str = ""
    description: str = ""
    hidden: bool = False
    ConfigModel: Type[BaseModel] = EmptyConfig

    def __init__(self, config: BaseModel):
        self.config = config

    def test(self) -> Tuple[bool, str]:
        """连接/可用性自检。基类默认无需测试；子类可覆写做实测。"""
        return True, "该插件无需连接测试"

    def close(self) -> None:
        """释放插件持有的资源（HTTP 连接等）。基类默认无操作；

        持有连接的子类应覆写。热重载替换实例前会调用，避免连接/fd 泄漏。
        """

    def __repr__(self) -> str:  # pragma: no cover - 便于调试
        return f"<{self.category}:{self.name}>"


class Parser(Plugin):
    """解析器：从文件名提取结构化信息（标题/季/集/年）。"""

    category = "parser"

    @abstractmethod
    def parse(self, name: str) -> Optional[ParseResult]:
        """解析文件名；无法解析返回 None（交给链中下一个解析器）。"""
        raise NotImplementedError


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
    """下载器：把 Release 投递给下载客户端。

    supports_management=True 表示该下载器实现了任务查询/控制接口
    （list_tasks/remove/pause/resume/add_uri），Web 下载管理页据此展示操作按钮。
    默认 False：基类各管理方法为空实现（如 dummy 测试下载器）。
    """

    category = "downloader"
    supports_management: bool = False

    @abstractmethod
    def add(self, release: Release) -> bool:
        """提交下载，成功返回 True。"""
        raise NotImplementedError

    def list_completed(self) -> List[Path]:
        """返回已完成任务的文件/目录路径（可选，便于闭环）。"""
        return []

    # ---- 以下为下载管理接口（可选）：默认「不支持」，实现了的下载器覆写 ----
    def list_tasks(self) -> List[DownloadTask]:
        """列出当前所有任务（归一化为 DownloadTask）。默认空。"""
        return []

    def remove(self, task_id: str, delete_files: bool = False) -> bool:
        """删除任务；delete_files=True 时连同已下载文件删除。默认不支持。"""
        return False

    def pause(self, task_id: str) -> bool:
        """暂停任务。默认不支持。"""
        return False

    def resume(self, task_id: str) -> bool:
        """恢复任务。默认不支持。"""
        return False

    def add_uri(self, uri: str, save_path: Optional[str] = None) -> bool:
        """以磁力/种子/HTTP 链接手动新建下载。默认不支持。"""
        return False


class Notifier(Plugin):
    """通知器：推送事件。"""

    category = "notifier"

    @abstractmethod
    def notify(self, event: Event) -> None:
        raise NotImplementedError

    def test(self) -> Tuple[bool, str]:
        """发送一条测试通知。"""
        try:
            self.notify(Event("info", "MediaMaid 连接测试"))
            return True, "已发送测试通知（请到接收端确认）"
        except Exception as e:  # noqa: BLE001
            return False, f"发送失败: {e}"


class MediaServer(Plugin):
    """媒体服务器：整理后刷新媒体库，并可查询库中是否已有某资源（去重数据源）。"""

    category = "mediaserver"

    def refresh(self) -> bool:
        """触发媒体库扫描刷新。默认无操作，子类覆写。"""
        return False

    def exists(self, item: MediaItem, info: Optional[MediaInfo] = None) -> bool:
        """查询库中是否已存在该影片/剧集。默认 False（best-effort，子类覆写）。"""
        return False


# 类别名 -> 基类，供 registry 校验插件归属
CATEGORIES = {
    Parser.category: Parser,
    Scraper.category: Scraper,
    Subscriber.category: Subscriber,
    Downloader.category: Downloader,
    Notifier.category: Notifier,
    MediaServer.category: MediaServer,
}
