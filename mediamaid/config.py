"""配置加载与校验（pydantic + YAML）。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

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


class SubscriptionFilter(BaseModel):
    """订阅的质量过滤/择优规则，对任意订阅器产出的 Release 通用。"""

    # 非空时：标题须包含其一（不区分大小写），如 ["1080p", "2160p"]
    resolutions: List[str] = Field(default_factory=list)
    # 须全部命中（不区分大小写）
    include_keywords: List[str] = Field(default_factory=list)
    # 命中任一则丢弃
    exclude_keywords: List[str] = Field(default_factory=list)
    # 包含正则：非空时，标题须匹配该正则才处理（不区分大小写；正则非法时退化为子串包含）
    include_regex: Optional[str] = None
    # 排除正则：非空时，标题匹配该正则即丢弃（不区分大小写；正则非法时退化为子串包含）
    exclude_regex: Optional[str] = None
    # 体积区间（MB），None 表示不限
    min_size_mb: Optional[int] = None
    max_size_mb: Optional[int] = None
    # 择优优先级关键词：靠前者优先；同一集多候选时据此选最佳
    prefer: List[str] = Field(default_factory=list)


class Subscription(BaseModel):
    """一条命名订阅：选定某订阅器类型并提供其参数。"""

    id: str
    name: str
    subscriber: str  # 订阅器类型名，如 "rss"
    enabled: bool = True
    config: Dict = Field(default_factory=dict)
    # 选定的下载器插件名（如 "qbittorrent"）；None 表示用所有启用下载器（首个成功者胜，兼容旧配置）
    downloader: Optional[str] = None
    # 质量过滤/择优规则
    filters: SubscriptionFilter = Field(default_factory=SubscriptionFilter)
    # 是否查媒体服务器跳过"已拥有"的资源
    skip_existing: bool = True


class IgnoreEpisodes(BaseModel):
    """某 TMDB 条目下，某一季里要忽略的具体集号。"""

    season: int
    episodes: List[int] = Field(default_factory=list)


class TmdbRule(BaseModel):
    """一条 TMDB 规则：把命中正则的文件钉到某个 tmdb_id，并/或忽略其某些季集。

    - patterns 命中 → 直接绑定到 tmdb_id（跳过按标题搜索），季/集由 season 或正则组提供。
    - ignore_seasons / ignore_episodes → 该 tmdb_id 命中时不整理（绑定与自动匹配都适用）。
    两者皆可独立存在：只填 patterns（纯绑定）、只填 ignore（纯过滤）、或两者兼有。
    """

    id: str
    tmdb_id: int
    title: str = ""  # 显示标签（从 TMDB 拉来缓存，仅 UI 展示）
    media_type: str = "episode"  # movie / episode
    category: str = "tv"  # tv / anime（剧集落地目录）
    enabled: bool = True
    # 绑定：命中任一正则 → 钉到此 tmdb_id；正则可含 (?P<season>)(?P<episode>)
    patterns: List[str] = Field(default_factory=list)
    # 固定季号；为空则用正则的 (?P<season>)，仍无则剧集默认第 1 季
    season: Optional[int] = None
    # 忽略：整季 / 按季忽略具体集
    ignore_seasons: List[int] = Field(default_factory=list)
    ignore_episodes: List[IgnoreEpisodes] = Field(default_factory=list)


class Config(BaseModel):
    # 监控/扫描的源目录（可多个）
    source_dirs: List[Path]
    # 媒体库根目录
    library_dir: Path
    # 转移失败目录：整理失败的文件移此隔离，扫描/监控不再自动处理（避免反复重试）。
    # None 表示不启用（失败文件留在原地）。建议放在 source_dirs 之外。
    failed_dir: Optional[Path] = None
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

    # TMDB 规则：正则命中 → 直接绑定到某 tmdb_id；并可忽略其某些季集。
    # 取代旧的「顺序正则解析器」；未命中规则的文件仍由内置 guessit 解析后按标题搜索。
    tmdb_rules: List[TmdbRule] = Field(default_factory=list)

    def under_failed(self, path: Path) -> bool:
        """path 是否位于转移失败目录内（含目录本身）。未配置 failed_dir 时恒 False。"""
        if self.failed_dir is None:
            return False
        try:
            fd = Path(self.failed_dir).resolve()
            p = Path(path).resolve()
        except OSError:
            return False
        return p == fd or fd in p.parents

    def plugin_specs(self, category: str) -> List[PluginSpec]:
        """返回某类别下 enabled 的插件实例配置。"""
        return [s for s in self.plugins.get(category, []) if s.enabled]

    def enabled_subscriptions(self) -> List[Subscription]:
        return [s for s in self.subscriptions if s.enabled]

    def enabled_tmdb_rules(self) -> List[TmdbRule]:
        return [r for r in self.tmdb_rules if r.enabled]

    def is_ignored(
        self, tmdb_id: int, season: Optional[int], episode: Optional[int]
    ) -> bool:
        """该 tmdb_id 的 (season, episode) 是否被某条启用规则忽略。"""
        for r in self.tmdb_rules:
            if not r.enabled or r.tmdb_id != tmdb_id:
                continue
            if season is not None and season in r.ignore_seasons:
                return True
            for ie in r.ignore_episodes:
                if ie.season == season and episode is not None and episode in ie.episodes:
                    return True
        return False


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
