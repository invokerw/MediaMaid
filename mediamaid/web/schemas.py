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


class SubscriptionFilterBody(BaseModel):
    resolutions: Optional[List[str]] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    min_size_mb: Optional[int] = None
    max_size_mb: Optional[int] = None
    prefer: Optional[List[str]] = None


class SubscriptionBody(BaseModel):
    name: str
    subscriber: str
    enabled: bool = True
    config: dict = {}
    filters: Optional[SubscriptionFilterBody] = None
    skip_existing: Optional[bool] = None


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    subscriber: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    filters: Optional[SubscriptionFilterBody] = None
    skip_existing: Optional[bool] = None


class ParserBody(BaseModel):
    name: str
    parser: str
    enabled: bool = True
    config: dict = {}


class ParserUpdate(BaseModel):
    name: Optional[str] = None
    parser: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None


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
