"""Web API 的请求体模型（pydantic）。集中放置，供各 router 复用。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ScanBody(BaseModel):
    dry_run: bool = False


class PluginBody(BaseModel):
    enabled: bool = True
    config: dict = {}


class TestBody(BaseModel):
    config: dict = {}


class ReleaseBody(BaseModel):
    title: str
    guid: str
    magnet: Optional[str] = None
    torrent_url: Optional[str] = None
    link: Optional[str] = None
    sub_id: Optional[str] = None


class ReleasesBatchBody(BaseModel):
    """批量操作（下载 / 标记已处理）一组资源；每条携带自己的 sub_id。"""

    releases: List[ReleaseBody] = []


class SubscriptionFilterBody(BaseModel):
    resolutions: Optional[List[str]] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    include_regex: Optional[str] = None
    exclude_regex: Optional[str] = None
    min_size_mb: Optional[int] = None
    max_size_mb: Optional[int] = None
    prefer: Optional[List[str]] = None


class SubscriptionBody(BaseModel):
    name: str
    subscriber: str
    enabled: bool = True
    downloader: Optional[str] = None
    config: dict = {}
    filters: Optional[SubscriptionFilterBody] = None
    skip_existing: Optional[bool] = None


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    subscriber: Optional[str] = None
    enabled: Optional[bool] = None
    downloader: Optional[str] = None
    config: Optional[dict] = None
    filters: Optional[SubscriptionFilterBody] = None
    skip_existing: Optional[bool] = None


class IgnoreEpisodesBody(BaseModel):
    season: int
    episodes: List[int] = []


class TmdbRuleBody(BaseModel):
    """新建/全量编辑一条 TMDB 规则。"""

    tmdb_id: int
    title: str = ""
    media_type: str = "episode"  # movie / episode
    category: str = "tv"  # tv / anime
    enabled: bool = True
    patterns: List[str] = []
    season: Optional[int] = None
    ignore_seasons: List[int] = []
    ignore_episodes: List[IgnoreEpisodesBody] = []


class TmdbRuleUpdate(BaseModel):
    """部分更新一条 TMDB 规则；仅提交的字段被改。"""

    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    media_type: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None
    patterns: Optional[List[str]] = None
    season: Optional[int] = None
    ignore_seasons: Optional[List[int]] = None
    ignore_episodes: Optional[List[IgnoreEpisodesBody]] = None


class ParseTestBody(BaseModel):
    name: str


class NewDownloadBody(BaseModel):
    """下载管理页手动新建下载。"""

    downloader: str
    uri: str  # 磁力 / 种子 URL / HTTP 链接
    save_path: Optional[str] = None


class DeleteBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    path: str
    name: str


class OrganizeIdentifyBody(BaseModel):
    """对单个源文件做识别 + TMDB 自动匹配预览（不落地）。"""

    path: str


class OrganizeManualBody(BaseModel):
    """手动转移：按用户指定的 TMDB 条目刮削并落地。"""

    path: str
    tmdb_id: int
    media_type: str  # "movie" / "episode"
    season: Optional[int] = None
    episode: Optional[int] = None
    category: Optional[str] = None  # 剧集分类："tv" / "anime"


class FiltersBody(BaseModel):
    video_extensions: Optional[List[str]] = None
    min_size_mb: Optional[int] = None
    exclude_keywords: Optional[List[str]] = None


class NamingBody(BaseModel):
    movie: Optional[str] = None
    episode: Optional[str] = None
    movie_no_year: Optional[str] = None
    episode_no_year: Optional[str] = None
    anime: Optional[str] = None
    anime_no_year: Optional[str] = None


class SettingsBody(BaseModel):
    """顶层可编辑设置，全部可选；仅提交的字段会被更新。"""

    source_dirs: Optional[List[str]] = None
    library_dir: Optional[str] = None
    action: Optional[str] = None
    on_conflict: Optional[str] = None
    stable_seconds: Optional[int] = None
    rescan_interval: Optional[int] = None
    subscribe_interval: Optional[int] = None
    poll_completed: Optional[bool] = None
    poll_interval: Optional[int] = None
    write_nfo: Optional[bool] = None
    download_artwork: Optional[bool] = None
    anime_keywords: Optional[List[str]] = None
    filters: Optional[FiltersBody] = None
    naming: Optional[NamingBody] = None
