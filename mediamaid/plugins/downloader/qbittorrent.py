"""qBittorrent 下载器：通过 Web API 提交磁力/种子。

依赖 qbittorrent-api（可选，pip install 'mediamaid[plugins]'），惰性 import。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Release
from ..base import Downloader
from ..registry import register

log = get_logger(__name__)


class QbittorrentConfig(BaseModel):
    host: str = "localhost"
    port: int = 8080
    username: str = "admin"
    password: str = "adminadmin"
    # 提交时打的分类；可配合 qB「按分类设保存路径」使其落到源目录
    category: str = "mediamaid"
    save_path: Optional[str] = None
    # 跨容器路径映射，每项 "远端前缀:本地前缀"（如 "/downloads:/data/downloads"）。
    # 仅当下载器上报路径与 MediaMaid 视角不一致时需要（poll_completed 模式）。
    path_mappings: list[str] = []


@register
class QbittorrentDownloader(Downloader):
    name = "qbittorrent"
    ConfigModel = QbittorrentConfig

    def __init__(self, config: QbittorrentConfig):
        super().__init__(config)
        self._client = None
        # 解析为 [(远端前缀, 本地前缀)]，按远端前缀长度降序（最长匹配优先）
        self._maps = []
        for m in config.path_mappings:
            if ":" in m:
                remote, local = m.split(":", 1)
                if remote and local:
                    self._maps.append((remote.rstrip("/"), local.rstrip("/")))
        self._maps.sort(key=lambda x: len(x[0]), reverse=True)

    def _map_path(self, p: str) -> str:
        """把下载器上报的远端路径转换为 MediaMaid 本地路径。"""
        for remote, local in self._maps:
            if p == remote or p.startswith(remote + "/"):
                return local + p[len(remote):]
        return p

    def _conn(self):
        if self._client is not None:
            return self._client
        try:
            import qbittorrentapi  # 惰性 import
        except ImportError:
            log.error("qBittorrent 下载器需要 qbittorrent-api：pip install 'mediamaid[plugins]'")
            return None
        cfg: QbittorrentConfig = self.config
        client = qbittorrentapi.Client(
            host=cfg.host, port=cfg.port, username=cfg.username, password=cfg.password
        )
        try:
            client.auth_log_in()
        except Exception as e:  # noqa: BLE001
            log.error("qBittorrent 登录失败 %s:%s: %s", cfg.host, cfg.port, e)
            return None
        self._client = client
        return client

    def test(self):
        client = self._conn()
        if client is None:
            return False, "qBittorrent 登录失败：检查地址/账号密码或依赖是否安装"
        try:
            ver = client.app.version
        except Exception:  # noqa: BLE001
            ver = "?"
        return True, f"已连接 qBittorrent {ver}"

    def add(self, release: Release) -> bool:
        uri = release.download_uri
        if not uri:
            log.warning("Release 无可下载链接，跳过: %s", release.title)
            return False
        client = self._conn()
        if client is None:
            return False
        cfg: QbittorrentConfig = self.config
        try:
            result = client.torrents_add(
                urls=uri, category=cfg.category, save_path=cfg.save_path
            )
            ok = str(result).lower().startswith("ok")
            log.info("提交下载[%s] %s: %s", cfg.category, release.title, result)
            return ok
        except Exception as e:  # noqa: BLE001
            log.error("提交下载失败 %s: %s", release.title, e)
            return False

    def list_completed(self) -> List[Path]:
        client = self._conn()
        if client is None:
            return []
        cfg: QbittorrentConfig = self.config
        paths: List[Path] = []
        try:
            for t in client.torrents_info(category=cfg.category, status_filter="completed"):
                paths.append(Path(self._map_path(str(t.content_path))))
        except Exception as e:  # noqa: BLE001
            log.error("查询完成任务失败: %s", e)
        return paths
