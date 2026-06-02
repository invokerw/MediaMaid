"""Transmission 下载器：通过 RPC 提交磁力/种子并查询完成任务。

依赖 transmission-rpc（可选）。惰性 import，缺失时经 deps.require 自动安装。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import DownloadTask, Release
from ..base import Downloader
from ..deps import require
from ..registry import register
from . import PathMapper

log = get_logger(__name__)

# Transmission 任务状态 -> 归一化状态
_STATE_MAP = {
    "downloading": "downloading",
    "download pending": "queued",
    "seeding": "seeding",
    "seed pending": "queued",
    "checking": "queued",
    "check pending": "queued",
    "stopped": "paused",
}


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
    description = "Transmission 下载器，通过 RPC 提交磁力/种子并查询完成任务"
    supports_management = True
    ConfigModel = TransmissionConfig

    def __init__(self, config: TransmissionConfig):
        super().__init__(config)
        self._client = None
        self._mapper = PathMapper(config.path_mappings)
        # 最近一次连接失败原因（缺依赖 / 连接失败等），供 test() 精确回显
        self._conn_error: Optional[str] = None

    def _conn(self):
        if self._client is not None:
            return self._client
        mod, err = require("transmission_rpc", "transmission-rpc")  # 缺失则自动安装
        if mod is None:
            log.error("Transmission 下载器依赖不可用: %s", err)
            self._conn_error = err
            return None
        cfg: TransmissionConfig = self.config
        try:
            client = mod.Client(
                protocol=cfg.protocol,
                host=cfg.host,
                port=cfg.port,
                path=cfg.path,
                username=cfg.username,
                password=cfg.password,
            )
        except Exception as e:  # noqa: BLE001
            detail = str(e) or type(e).__name__
            log.error("Transmission 连接失败 %s:%s: %s", cfg.host, cfg.port, detail)
            self._conn_error = f"连接失败 {cfg.host}:{cfg.port}: {detail}"
            return None
        self._client = client
        self._conn_error = None
        return client

    def close(self) -> None:
        # transmission-rpc 无显式会话需关闭，丢弃引用即可
        self._client = None

    def test(self):
        client = self._conn()
        if client is None:
            return False, self._conn_error or "Transmission 连接失败：检查地址/账号密码"
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
        return self.add_uri(uri)

    def add_uri(self, uri: str, save_path: Optional[str] = None) -> bool:
        if not uri:
            return False
        client = self._conn()
        if client is None:
            return False
        try:
            client.add_torrent(uri, download_dir=save_path)
            log.info("提交下载 %s", uri[:60])
            return True
        except Exception as e:  # noqa: BLE001
            log.error("提交下载失败 %s: %s", uri[:60], e)
            return False

    @staticmethod
    def _eta_seconds(t) -> Optional[int]:
        """transmission-rpc 的 eta 可能是 timedelta 或 int(秒)；负值表示未知。"""
        eta = getattr(t, "eta", None)
        if eta is None:
            return None
        try:
            secs = int(eta.total_seconds()) if hasattr(eta, "total_seconds") else int(eta)
        except (TypeError, ValueError):
            return None
        return secs if secs >= 0 else None

    def list_tasks(self) -> List[DownloadTask]:
        client = self._conn()
        if client is None:
            return []
        tasks: List[DownloadTask] = []
        try:
            for t in client.get_torrents():
                status = str(getattr(t, "status", "")).lower()
                err = getattr(t, "error_string", "") or None
                tasks.append(
                    DownloadTask(
                        id=str(t.id),
                        name=str(t.name),
                        state="error" if err else _STATE_MAP.get(status, "unknown"),
                        progress=float(getattr(t, "percent_done", 0.0) or 0.0),
                        size=int(getattr(t, "total_size", 0) or 0) or None,
                        downloaded=int(getattr(t, "downloaded_ever", 0) or 0) or None,
                        dl_speed=int(getattr(t, "rate_download", 0) or 0),
                        up_speed=int(getattr(t, "rate_upload", 0) or 0),
                        eta=self._eta_seconds(t),
                        error=err,
                    )
                )
        except Exception as e:  # noqa: BLE001
            log.error("查询任务列表失败: %s", e)
        return tasks

    def remove(self, task_id: str, delete_files: bool = False) -> bool:
        client = self._conn()
        if client is None:
            return False
        try:
            client.remove_torrent(int(task_id), delete_data=delete_files)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("删除任务失败 %s: %s", task_id, e)
            return False

    def pause(self, task_id: str) -> bool:
        client = self._conn()
        if client is None:
            return False
        try:
            client.stop_torrent(int(task_id))
            return True
        except Exception as e:  # noqa: BLE001
            log.error("暂停任务失败 %s: %s", task_id, e)
            return False

    def resume(self, task_id: str) -> bool:
        client = self._conn()
        if client is None:
            return False
        try:
            client.start_torrent(int(task_id))
            return True
        except Exception as e:  # noqa: BLE001
            log.error("恢复任务失败 %s: %s", task_id, e)
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
