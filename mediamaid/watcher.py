"""监控守护：watchdog 监听 + 文件稳定性检测 + 定时兜底扫描。"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .logging_conf import get_logger
from .pipeline import Pipeline

log = get_logger(__name__)


class _Handler(FileSystemEventHandler):
    """收集文件事件，交给稳定性队列。"""

    def __init__(self, on_candidate):
        self._on_candidate = on_candidate

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._on_candidate(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._on_candidate(Path(event.dest_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._on_candidate(Path(event.src_path))


class Watcher:
    """常驻监控。文件大小连续 stable_seconds 不变才认为写入完成再处理。"""

    def __init__(self, config: Config, pipeline: Pipeline):
        self.config = config
        self.pipeline = pipeline
        self._pending: Dict[Path, tuple] = {}  # path -> (size, last_change_ts)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._observer = Observer()

    def _on_candidate(self, path: Path) -> None:
        # 失败目录里的文件不自动处理（失败目录若位于某源目录内）
        if self.config.under_failed(path):
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        with self._lock:
            self._pending[path] = (size, time.monotonic())

    def _stability_loop(self) -> None:
        """周期检查待定文件，体积稳定且超过阈值则处理。"""
        while not self._stop.is_set():
            now = time.monotonic()
            ready = []
            with self._lock:
                for path, (size, ts) in list(self._pending.items()):
                    try:
                        cur = path.stat().st_size
                    except OSError:
                        # 文件消失，丢弃
                        self._pending.pop(path, None)
                        continue
                    if cur != size:
                        self._pending[path] = (cur, now)  # 仍在变化，重置计时
                    elif now - ts >= self.config.stable_seconds:
                        ready.append(path)
                        self._pending.pop(path, None)
            for path in ready:
                self._process(path)
            self._stop.wait(2.0)

    def _process(self, path: Path) -> None:
        try:
            result = self.pipeline.process_path(path)
            if result and result.status == "done":
                log.info("已整理: %s -> %s", path.name, result.dest)
                self.pipeline.refresh_media_servers()
        except Exception as e:  # noqa: BLE001
            log.error("处理失败 %s: %s", path, e)

    def _rescan_loop(self) -> None:
        interval = self.config.rescan_interval
        if interval <= 0:
            return
        while not self._stop.is_set():
            if self._stop.wait(interval):
                break
            log.info("兜底全量重扫…")
            try:
                self.pipeline.scan()
            except Exception as e:  # noqa: BLE001
                log.error("兜底扫描失败: %s", e)

    def start_background(self) -> None:
        """启动监控但不阻塞：初始全量扫描 + 挂观察者 + 起后台线程。

        供 Daemon 编排复用；独立 watch 命令用 start()。
        """
        log.info("启动时全量扫描…")
        self.pipeline.scan()

        handler = _Handler(self._on_candidate)
        for src in self.config.source_dirs:
            src = Path(src)
            if not src.exists():
                log.warning("源目录不存在，跳过监控: %s", src)
                continue
            self._observer.schedule(handler, str(src), recursive=True)
            log.info("监控目录: %s", src)
        self._observer.start()

        threading.Thread(target=self._stability_loop, daemon=True).start()
        threading.Thread(target=self._rescan_loop, daemon=True).start()

    def start(self) -> None:
        """独立运行监控守护（阻塞至 Ctrl-C）。"""
        self.start_background()
        log.info("MediaMaid 守护进程运行中（Ctrl-C 退出）")
        try:
            while not self._stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("收到中断，正在停止…")
        finally:
            self.stop()

    def reload(self, config: Config) -> None:
        """热重载：更新配置；若源目录变化则重挂监控。"""
        old_dirs = [str(p) for p in self.config.source_dirs]
        new_dirs = [str(p) for p in config.source_dirs]
        self.config = config
        if old_dirs != new_dirs and self._observer.is_alive():
            self._observer.unschedule_all()
            handler = _Handler(self._on_candidate)
            for src in config.source_dirs:
                src = Path(src)
                if not src.exists():
                    log.warning("源目录不存在，跳过监控: %s", src)
                    continue
                self._observer.schedule(handler, str(src), recursive=True)
                log.info("重挂监控目录: %s", src)

    def stop(self) -> None:
        self._stop.set()
        self._observer.stop()
        self._observer.join(timeout=5)
