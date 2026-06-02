"""Emby / Jellyfin 媒体服务器插件。

二者 HTTP API 几乎一致（均源自 MediaBrowser），用同一实现：
- 整理后触发媒体库刷新；
- 按标题查询库中是否已有该影片/剧集，供订阅"已拥有去重"。

均通过 `?api_key=` 查询参数鉴权（Emby/Jellyfin 通用）。
"""

from __future__ import annotations

from typing import Optional

import httpx
from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import MediaInfo, MediaItem, MediaType
from ..base import MediaServer
from ..registry import register
from ..scraper import title_similarity

log = get_logger(__name__)


class EmbyConfig(BaseModel):
    # 服务器地址，含协议与端口，如 http://192.168.1.10:8096
    base_url: str
    api_key: str
    timeout: float = 15.0
    # emby / jellyfin：仅影响日志展示，接口一致
    server_type: str = "emby"
    # 已拥有判定的标题相似度阈值
    match_threshold: float = 0.8


@register
class EmbyMediaServer(MediaServer):
    name = "emby"
    ConfigModel = EmbyConfig

    def __init__(self, config: EmbyConfig):
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)
        self._base = config.base_url.rstrip("/")

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - 关闭尽力而为
            pass

    def _get(self, path: str, **params) -> Optional[dict]:
        params.setdefault("api_key", self.config.api_key)
        try:
            resp = self.client.get(f"{self._base}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            log.warning("%s 请求失败 %s: %s", self.config.server_type, path, e)
            return None

    def test(self):
        data = self._get("/System/Info")
        if data and data.get("Version"):
            name = data.get("ServerName", "?")
            return True, f"已连接 {self.config.server_type} {name} {data['Version']}"
        return False, f"{self.config.server_type} 连接失败：检查地址或 api_key"

    def refresh(self) -> bool:
        """触发全库扫描刷新（Emby/Jellyfin 均为 POST /Library/Refresh）。"""
        try:
            resp = self.client.post(
                f"{self._base}/Library/Refresh", params={"api_key": self.config.api_key}
            )
            resp.raise_for_status()
            log.info("%s 媒体库刷新已触发", self.config.server_type)
            return True
        except httpx.HTTPError as e:
            log.warning("%s 媒体库刷新失败: %s", self.config.server_type, e)
            return False

    def exists(self, item: MediaItem, info: Optional[MediaInfo] = None) -> bool:
        """库中是否已有该影片/剧集。

        剧集仅判定"该剧是否存在"（集级精确判定成本高），电影按标题+年份比对。
        """
        title = (info.title if info and info.title else item.title) or ""
        if not title:
            return False
        year = (info.year if info and info.year else item.year)
        kinds = "Movie" if item.media_type == MediaType.MOVIE else "Series"
        data = self._get(
            "/Items",
            Recursive="true",
            searchTerm=title,
            IncludeItemTypes=kinds,
            Fields="ProductionYear",
            Limit=20,
        )
        if not data:
            return False
        for it in data.get("Items", []):
            name = it.get("Name", "")
            if title_similarity(title, name) < self.config.match_threshold:
                continue
            iy = it.get("ProductionYear")
            if year and iy and int(iy) != int(year):
                continue
            log.debug("媒体库已存在: %s (%s)", name, iy)
            return True
        return False
