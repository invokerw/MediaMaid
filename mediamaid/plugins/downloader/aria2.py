"""aria2 下载器：通过 JSON-RPC 提交磁力/种子链接。

直接用 httpx 调 aria2 的 JSON-RPC（无需额外依赖）。

注意：aria2 对种子下载完成后的内容路径上报较弱，list_completed 为 best-effort——
推荐配合 watcher 监控保存目录来衔接整理，而非依赖 poll_completed。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import httpx
from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import DownloadTask, Release
from ..base import Downloader
from ..registry import register
from . import PathMapper

log = get_logger(__name__)

# aria2 任务状态 -> 归一化状态
_STATE_MAP = {
    "active": "downloading",
    "waiting": "queued",
    "paused": "paused",
    "complete": "completed",
    "error": "error",
    "removed": "error",
}


class Aria2Config(BaseModel):
    host: str = "localhost"
    port: int = 6800
    # RPC secret（aria2c --rpc-secret），无则留空
    secret: Optional[str] = None
    protocol: str = "http"
    rpc_path: str = "/jsonrpc"
    timeout: float = 15.0
    # 跨容器路径映射，每项 "远端前缀:本地前缀"
    path_mappings: list[str] = []


@register
class Aria2Downloader(Downloader):
    name = "aria2"
    description = "aria2 下载器，通过 JSON-RPC 提交磁力/种子链接"
    supports_management = True
    ConfigModel = Aria2Config

    def __init__(self, config: Aria2Config):
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)
        self._mapper = PathMapper(config.path_mappings)
        self._url = f"{config.protocol}://{config.host}:{config.port}{config.rpc_path}"

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - 关闭尽力而为
            pass

    def _call(self, method: str, *params):
        """调用一个 aria2 RPC 方法；secret 作为首个 token 参数。"""
        token = [f"token:{self.config.secret}"] if self.config.secret else []
        payload = {
            "jsonrpc": "2.0",
            "id": "mediamaid",
            "method": method,
            "params": token + list(params),
        }
        resp = self.client.post(self._url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "aria2 RPC error"))
        return data.get("result")

    def test(self):
        try:
            ver = self._call("aria2.getVersion")
        except Exception as e:  # noqa: BLE001
            return False, f"aria2 连接失败: {e}"
        return True, f"已连接 aria2 {ver.get('version', '?')}"

    def add(self, release: Release) -> bool:
        uri = release.download_uri
        if not uri:
            log.warning("Release 无可下载链接，跳过: %s", release.title)
            return False
        return self.add_uri(uri)

    def add_uri(self, uri: str, save_path: Optional[str] = None) -> bool:
        if not uri:
            return False
        try:
            params = [[uri]]
            if save_path:
                params.append({"dir": save_path})
            self._call("aria2.addUri", *params)
            log.info("提交下载 %s", uri[:60])
            return True
        except Exception as e:  # noqa: BLE001
            log.error("提交下载失败 %s: %s", uri[:60], e)
            return False

    @staticmethod
    def _task_name(task: dict) -> str:
        bt = task.get("bittorrent") or {}
        info = bt.get("info") or {}
        if info.get("name"):
            return str(info["name"])
        files = task.get("files") or []
        if files and files[0].get("path"):
            return Path(files[0]["path"]).name
        return task.get("gid", "")

    def list_tasks(self) -> List[DownloadTask]:
        keys = [
            "gid",
            "status",
            "totalLength",
            "completedLength",
            "downloadSpeed",
            "uploadSpeed",
            "files",
            "bittorrent",
            "errorMessage",
        ]
        tasks: List[DownloadTask] = []
        try:
            active = self._call("aria2.tellActive", keys) or []
            waiting = self._call("aria2.tellWaiting", 0, 1000, keys) or []
            stopped = self._call("aria2.tellStopped", 0, 1000, keys) or []
        except Exception as e:  # noqa: BLE001
            log.error("查询任务列表失败: %s", e)
            return tasks
        for task in [*active, *waiting, *stopped]:
            try:
                total = int(task.get("totalLength", 0) or 0)
                done = int(task.get("completedLength", 0) or 0)
                speed = int(task.get("downloadSpeed", 0) or 0)
                progress = (done / total) if total else 0.0
                eta = int((total - done) / speed) if (speed and total) else None
                status = str(task.get("status", ""))
                err = task.get("errorMessage") or None
                tasks.append(
                    DownloadTask(
                        id=str(task.get("gid", "")),
                        name=self._task_name(task),
                        state=_STATE_MAP.get(status, "unknown"),
                        progress=progress,
                        size=total or None,
                        downloaded=done or None,
                        dl_speed=speed,
                        up_speed=int(task.get("uploadSpeed", 0) or 0),
                        eta=eta,
                        error=err,
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.error("解析 aria2 任务失败: %s", e)
        return tasks

    def remove(self, task_id: str, delete_files: bool = False) -> bool:
        if delete_files:
            # aria2 无法在删除任务时一并删除已下载文件，仅移除任务记录
            log.warning("aria2 不支持连同文件删除，仅移除任务: %s", task_id)
        try:
            # 进行中/等待/暂停用 remove，已停止用 removeDownloadResult
            try:
                self._call("aria2.remove", task_id)
            except Exception:  # noqa: BLE001 - 已停止的任务改用结果清理
                self._call("aria2.removeDownloadResult", task_id)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("删除任务失败 %s: %s", task_id, e)
            return False

    def pause(self, task_id: str) -> bool:
        try:
            self._call("aria2.pause", task_id)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("暂停任务失败 %s: %s", task_id, e)
            return False

    def resume(self, task_id: str) -> bool:
        try:
            self._call("aria2.unpause", task_id)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("恢复任务失败 %s: %s", task_id, e)
            return False

    def list_completed(self) -> List[Path]:
        paths: List[Path] = []
        try:
            stopped = self._call("aria2.tellStopped", 0, 1000, ["status", "files"])
        except Exception as e:  # noqa: BLE001
            log.error("查询完成任务失败: %s", e)
            return paths
        for task in stopped or []:
            if task.get("status") != "complete":
                continue
            for f in task.get("files", []):
                p = f.get("path")
                if p:
                    paths.append(Path(self._mapper.map(p)))
        return paths
