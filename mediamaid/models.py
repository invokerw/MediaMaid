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


@dataclass
class MediaItem:
    """识别阶段产物：源文件 + 从文件名解析出的信息。"""

    source: Path
    media_type: MediaType
    title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
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
    overview: Optional[str] = None
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
class Event:
    """通知事件，交给通知器(Notifier)。"""

    type: str  # organized / download_added / error / info
    message: str
    item: Optional[MediaItem] = None
    info: Optional[MediaInfo] = None
    dest: Optional[Path] = None
