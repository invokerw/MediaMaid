"""贯穿流水线的数据对象。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class MediaType(str, enum.Enum):
    MOVIE = "movie"
    EPISODE = "episode"
    UNKNOWN = "unknown"


class TransferAction(str, enum.Enum):
    HARDLINK = "hardlink"
    COPY = "copy"
    MOVE = "move"
    SYMLINK = "symlink"


@dataclass
class MediaItem:
    """识别阶段产物：源文件 + 从文件名解析出的信息。"""

    source: Path
    media_type: MediaType
    title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    # 命中 TMDB 绑定规则时携带，刮削阶段据此直查（绕过搜索）
    tmdb_id: Optional[int] = None
    # 分类：剧集可为 "tv" / "anime"，决定落地到 TV/ 还是 Anime/ 目录。
    # None=自动（落地阶段按 TMDB 题材判定）；非空=显式指定（如 TMDB 绑定规则/手动转移）。
    category: Optional[str] = None
    # guessit 的原始解析结果，保留以备调试 / 进阶匹配
    raw: dict = field(default_factory=dict)

    @property
    def ext(self) -> str:
        return self.source.suffix.lstrip(".").lower()


@dataclass
class MediaInfo:
    """刮削阶段产物：来自元数据源（如 TMDB）的权威信息。"""

    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    # 外部 ID：写入 nfo 可显著提升 Jellyfin/Emby 匹配率
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    overview: Optional[str] = None
    genres: list = field(default_factory=list)
    # TMDB 题材 ID 列表（16=动画），用于按题材判定动漫
    genre_ids: list = field(default_factory=list)
    rating: Optional[float] = None
    # 剧集字段
    episode_title: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    poster_url: Optional[str] = None
    fanart_url: Optional[str] = None
    # 匹配置信度 0~1；低于阈值视为不可靠
    confidence: float = 0.0


@dataclass
class TransferPlan:
    """落地阶段计划：把 source 通过 action 放到 dest。"""

    item: MediaItem
    info: Optional[MediaInfo]
    source: Path
    dest: Path
    action: TransferAction


@dataclass
class ParseResult:
    """解析器从文件名提取出的结构化信息。"""

    type: MediaType
    title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    # TMDB 绑定规则命中时直接给出 tmdb_id（跳过按标题搜索）
    tmdb_id: Optional[int] = None
    # 分类覆盖（"tv"/"anime"）；None 表示由 Identifier 按路径关键词判定
    category: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class Release:
    """订阅器(Subscriber)发现的一个可下载资源，交给下载器(Downloader)。"""

    title: str
    # 唯一标识（去重用），通常是 RSS guid / 详情页链接
    guid: str
    # 下载用链接：磁力或 .torrent URL（二者至少其一）
    magnet: Optional[str] = None
    torrent_url: Optional[str] = None
    link: Optional[str] = None  # 详情页
    size: Optional[int] = None  # 字节
    pub_date: Optional[str] = None
    source: Optional[str] = None  # 来源插件名/站点

    @property
    def download_uri(self) -> Optional[str]:
        return self.magnet or self.torrent_url


@dataclass
class DownloadTask:
    """下载器中一个任务的归一化视图（供 Web 下载管理页消费）。

    各下载器把自家字段映射成这套统一字段；progress 为 0~1，速度单位 B/s，
    eta 为秒（未知一律 None）。
    """

    id: str  # 下载器内的任务标识（qB 的 hash / Transmission 的 id / aria2 的 gid）
    name: str
    downloader: str = ""  # 来源下载器 name（聚合时由路由填充）
    # 归一化状态：downloading / paused / seeding / completed / queued / error / unknown
    state: str = "unknown"
    progress: float = 0.0  # 0~1
    size: Optional[int] = None  # 总字节
    downloaded: Optional[int] = None  # 已下载字节
    dl_speed: Optional[int] = None  # 下载速度 B/s
    up_speed: Optional[int] = None  # 上传速度 B/s
    eta: Optional[int] = None  # 预计剩余秒数，未知为 None
    error: Optional[str] = None


@dataclass
class Event:
    """通知事件，交给通知器(Notifier)。"""

    type: str  # organized / download_added / error / info
    message: str
    item: Optional[MediaItem] = None
    info: Optional[MediaInfo] = None
    dest: Optional[Path] = None
