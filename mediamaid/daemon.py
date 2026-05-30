"""全自动闭环守护进程：订阅→下载→（完成）→识别/刮削/整理→通知。

把 Watcher（源目录→整理）与 SubscribeRunner（订阅→下载）合成一个常驻进程：
- 订阅线程：周期 fetch 新资源并交给下载器；
- 监控：watchdog 监听源目录，下载完成的文件稳定后自动整理（天然衔接）；
- 完成轮询线程（可选）：周期查下载器已完成任务并主动整理，作为更稳健的完成信号。
"""

from __future__ import annotations

import threading
import time

from .config import Config
from .logging_conf import get_logger
from .pipeline import Pipeline
from .store import StateStore
from .subscribe import SubscribeRunner
from .watcher import Watcher

log = get_logger(__name__)


class Daemon:
    def __init__(self, config: Config, store: StateStore):
        self.config = config
        self.store = store
        self.pipeline = Pipeline(config, store)
        self.watcher = Watcher(config, self.pipeline)
        self.sub = SubscribeRunner(config, store, notify=self.pipeline.notify)
        self._stop = threading.Event()

    # ---- 订阅轮询 ----
    def _subscribe_loop(self) -> None:
        interval = max(1, self.config.subscribe_interval)
        # 立即跑一轮，之后按间隔
        while not self._stop.is_set():
            try:
                self.sub.run_once()
            except Exception as e:  # noqa: BLE001
                log.error("订阅轮询失败: %s", e)
            if self._stop.wait(interval):
                break

    # ---- 下载完成轮询 ----
    def _poll_completed_once(self) -> int:
        """遍历下载器已完成任务并整理，返回成功整理数。"""
        organized = 0
        for dl in self.sub.downloaders:
            try:
                paths = dl.list_completed()
            except Exception as e:  # noqa: BLE001
                log.error("查询下载器 %s 完成任务失败: %s", dl.name, e)
                continue
            for path in paths:
                for result in self.pipeline.process_target(path):
                    if result.status == "done":
                        organized += 1
        return organized

    def _completion_loop(self) -> None:
        interval = max(1, self.config.poll_interval)
        while not self._stop.is_set():
            try:
                self._poll_completed_once()
            except Exception as e:  # noqa: BLE001
                log.error("下载完成轮询失败: %s", e)
            if self._stop.wait(interval):
                break

    # ---- 生命周期 ----
    def run(self) -> None:
        log.info("启动 MediaMaid 闭环守护进程…")
        self.watcher.start_background()

        if self.sub.subscribers:
            threading.Thread(target=self._subscribe_loop, daemon=True).start()
            log.info("订阅轮询已启动（每 %ds）", self.config.subscribe_interval)
        else:
            log.info("未配置订阅器，跳过订阅轮询")

        if self.config.poll_completed and self.sub.downloaders:
            threading.Thread(target=self._completion_loop, daemon=True).start()
            log.info("下载完成轮询已启动（每 %ds）", self.config.poll_interval)

        log.info("闭环守护运行中（Ctrl-C 退出）")
        try:
            while not self._stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("收到中断，正在停止…")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        self.watcher.stop()
