"""配置加载与校验（pydantic + YAML）。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field

from .models import TransferAction


class FilterConfig(BaseModel):
    # 视频扩展名白名单
    video_extensions: List[str] = Field(
        default=["mkv", "mp4", "avi", "ts", "m2ts", "mov", "wmv", "flv", "iso"]
    )
    # 小于该体积(MB)的文件忽略（过滤 sample / 垃圾文件）
    min_size_mb: int = 50
    # 文件名包含这些关键词则跳过（不区分大小写）
    exclude_keywords: List[str] = Field(default=["sample", "trailer", "预告"])


class NamingConfig(BaseModel):
    # 模板可用占位符见 naming.py
    movie: str = "Movies/{title} ({year})/{title} ({year}).{ext}"
    episode: str = (
        "TV/{show} ({year})/Season {season:02d}/"
        "{show} - S{season:02d}E{episode:02d}.{ext}"
    )
    # 没有年份时的回退模板
    movie_no_year: str = "Movies/{title}/{title}.{ext}"
    episode_no_year: str = (
        "TV/{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}.{ext}"
    )
    # 动漫（剧集结构，单独 Anime/ 目录）
    anime: str = (
        "Anime/{show} ({year})/Season {season:02d}/"
        "{show} - S{season:02d}E{episode:02d}.{ext}"
    )
    anime_no_year: str = (
        "Anime/{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}.{ext}"
    )


class PluginSpec(BaseModel):
    """一个被启用的插件实例：名字 + 该插件自己的配置块。"""

    name: str
    enabled: bool = True
    config: Dict = Field(default_factory=dict)


class Subscription(BaseModel):
    """一条命名订阅：选定某订阅器类型并提供其参数。"""

    id: str
    name: str
    subscriber: str  # 订阅器类型名，如 "rss"
    enabled: bool = True
    config: Dict = Field(default_factory=dict)


class ParserSpec(BaseModel):
    """一条命名解析器：选定某解析器类型并提供其参数。链中按序尝试。"""

    id: str
    name: str
    parser: str  # 解析器类型名，如 "regex" / "guessit"
    enabled: bool = True
    config: Dict = Field(default_factory=dict)


class Config(BaseModel):
    # 监控/扫描的源目录（可多个）
    source_dirs: List[Path]
    # 媒体库根目录
    library_dir: Path
    # 默认落地方式
    action: TransferAction = TransferAction.HARDLINK
    # 同名目标已存在时：skip / overwrite / rename
    on_conflict: str = "skip"
    # 守护进程：文件大小连续 stable_seconds 秒不变才认为写入完成
    stable_seconds: int = 30
    # 守护进程：兜底全量重扫间隔（秒），0 表示关闭
    rescan_interval: int = 600
    # 闭环守护(run)：订阅轮询间隔（秒）
    subscribe_interval: int = 600
    # 闭环守护(run)：是否轮询下载器的已完成任务并主动整理
    poll_completed: bool = False
    # 闭环守护(run)：下载完成轮询间隔（秒）
    poll_interval: int = 300
    # 状态库路径
    state_db: Path = Path("mediamaid.db")
    # 全量扫描并发度：>1 时用线程池并行处理（瓶颈在 TMDB 网络请求）。
    # 注意 TMDB 速率限制，不宜过大。
    scan_workers: int = 4

    # 后处理选项（非某个插件专属）
    write_nfo: bool = False
    download_artwork: bool = False
    # 动漫归类关键词：源文件路径(含目录)命中任一关键词的剧集归入 Anime/。
    # 建议把动漫订阅的下载保存到名含 anime 的子目录，或填字幕组名等。
    anime_keywords: List[str] = Field(default_factory=list)

    filters: FilterConfig = Field(default_factory=FilterConfig)
    naming: NamingConfig = Field(default_factory=NamingConfig)

    # 插件配置：类别 -> 该类别启用的插件实例列表
    # 类别取值见 plugins.base.CATEGORIES：scraper/subscriber/downloader/notifier
    plugins: Dict[str, List[PluginSpec]] = Field(default_factory=dict)

    # 订阅条目：每条选一个订阅器类型 + 参数（取代 plugins.subscriber 的运行角色）
    subscriptions: List[Subscription] = Field(default_factory=list)

    # 解析器链：按序尝试，首个解析出标题者胜出；为空时回退内置 guessit
    parsers: List[ParserSpec] = Field(default_factory=list)

    def plugin_specs(self, category: str) -> List[PluginSpec]:
        """返回某类别下 enabled 的插件实例配置。"""
        return [s for s in self.plugins.get(category, []) if s.enabled]

    def enabled_subscriptions(self) -> List[Subscription]:
        return [s for s in self.subscriptions if s.enabled]

    def enabled_parsers(self) -> List[ParserSpec]:
        return [p for p in self.parsers if p.enabled]


def load_config(path: Path) -> Config:
    """从 YAML 文件加载配置。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)


class ConfigManager:
    """持有当前配置，按文件 mtime+size 自动热重载（线程安全）。

    Web 与守护进程都用它读配置：任一方写盘后，其他读取方下次 get() 自动感知。
    """

    def __init__(self, path: Path):
        import threading

        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp = None
        self._cfg: Config = None  # type: ignore[assignment]
        self.reload()

    def _file_stamp(self):
        try:
            st = self.path.stat()
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def reload(self) -> Config:
        with self._lock:
            self._cfg = load_config(self.path)
            self._stamp = self._file_stamp()
            return self._cfg

    def get(self) -> Config:
        """返回当前配置；若文件已变更则先自动重载。"""
        with self._lock:
            if self._file_stamp() != self._stamp:
                self._cfg = load_config(self.path)
                self._stamp = self._file_stamp()
            return self._cfg
