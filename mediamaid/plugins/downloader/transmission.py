"""Transmission 下载器：通过 RPC 提交磁力/种子并查询完成任务。

依赖 transmission-rpc（可选，pip install 'mediamaid[plugins]'），惰性 import。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Release
from ..base import Downloader
from ..registry import register
from . import PathMapper

log = get_logger(__name__)


class TransmissionConfig(BaseModel):
    host: str = "localhost"
    port: int = 9091
    username: Optional[str] = None
    password: Optional[str] = None
    # RPC 路径，默认 /transmission/rpc
    path: str = "/transmission/rpc"
    protocol: str = "http"
    # 跨容器路径映射，每项 "远端前缀:本地前缀"（poll_completed 模式用）
    path_mappings: list[str] = []


@register
class TransmissionDownloader(Downloader):
    name = "transmission"
    ConfigModel = TransmissionConfig

    def __init__(self, config: TransmissionConfig):
        super().__init__(config)
        self._client = None
        self._mapper = PathMapper(config.path_mappings)

    def _conn(self):
        if self._client is not None:
            return self._client
        try:
            from transmission_rpc import Client  # 惰性 import
        except ImportError:
            log.error(
                "Transmission 下载器需要 transmission-rpc：pip install 'mediamaid[plugins]'"
            )
            return None
        cfg: TransmissionConfig = self.config
        try:
            client = Client(
                protocol=cfg.protocol,
                host=cfg.host,
                port=cfg.port,
                path=cfg.path,
                username=cfg.username,
                password=cfg.password,
            )
        except Exception as e:  # noqa: BLE001
            log.error("Transmission 连接失败 %s:%s: %s", cfg.host, cfg.port, e)
            return None
        self._client = client
        return client

    def close(self) -> None:
        # transmission-rpc 无显式会话需关闭，丢弃引用即可
        self._client = None

    def test(self):
        client = self._conn()
        if client is None:
            return False, "Transmission 连接失败：检查地址/账号密码或依赖是否安装"
        try:
            ver = client.get_session().version
        except Exception as e:  # noqa: BLE001
            return False, f"Transmission 查询失败: {e}"
        return True, f"已连接 Transmission {ver}"

    def add(self, release: Release) -> bool:
        uri = release.download_uri
        if not uri:
            log.warning("Release 无可下载链接，跳过: %s", release.title)
            return False
        client = self._conn()
        if client is None:
            return False
        try:
            client.add_torrent(uri)
            log.info("提交下载 %s", release.title)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("提交下载失败 %s: %s", release.title, e)
            return False

    def list_completed(self) -> List[Path]:
        client = self._conn()
        if client is None:
            return []
        paths: List[Path] = []
        try:
            for t in client.get_torrents():
                if getattr(t, "percent_done", 0) >= 1.0:
                    download_dir = self._mapper.map(str(t.download_dir))
                    paths.append(Path(download_dir) / t.name)
        except Exception as e:  # noqa: BLE001
            log.error("查询完成任务失败: %s", e)
        return paths
