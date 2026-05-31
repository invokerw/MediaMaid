"""全自动闭环守护进程：订阅→下载→（完成）→识别/刮削/整理→通知。

把 Watcher（源目录→整理）与 SubscribeRunner（订阅→下载）合成一个常驻进程：
- 订阅线程：周期 fetch 新资源并交给下载器；
- 监控：watchdog 监听源目录，下载完成的文件稳定后自动整理（天然衔接）；
- 完成轮询线程（可选）：周期查下载器已完成任务并主动整理，作为更稳健的完成信号。
- 配置监视线程：config.yaml 变更后热重载，无需重启。
"""

from __future__ import annotations

import threading
import time

from .config import ConfigManager
from .logging_conf import get_logger
from .pipeline import Pipeline
from .store import StateStore
from .subscribe import SubscribeRunner
from .watcher import Watcher

log = get_logger(__name__)


class Daemon:
    def __init__(self, manager: ConfigManager, store: StateStore):
        self.manager = manager
        self.config = manager.get()
        self.store = store
        self.pipeline = Pipeline(self.config, store)
        self.watcher = Watcher(self.config, self.pipeline)
        self.sub = SubscribeRunner(self.config, store, notify=self.pipeline.notify)
        self._stop = threading.Event()

    # ---- 订阅轮询（每轮读当前间隔，使其热生效）----
    def _subscribe_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sub.run_once()
            except Exception as e:  # noqa: BLE001
                log.error("订阅轮询失败: %s", e)
            if self._stop.wait(max(1, self.config.subscribe_interval)):
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
        while not self._stop.is_set():
            if self.config.poll_completed:  # 每轮读，支持热开关
                try:
                    self._poll_completed_once()
                except Exception as e:  # noqa: BLE001
                    log.error("下载完成轮询失败: %s", e)
            if self._stop.wait(max(1, self.config.poll_interval)):
                break

    # ---- 配置监视：检测到变更则热重载 ----
    def _config_watch_loop(self) -> None:
        while not self._stop.is_set():
            if self._stop.wait(5):
                break
            new = self.manager.get()
            if new is self.config:
                continue
            log.info("检测到配置变更，热重载…")
            self.config = new
            try:
                self.pipeline.reload(new)
                self.sub.reload(new)
                self.watcher.reload(new)
                log.info("配置已重载")
            except Exception as e:  # noqa: BLE001
                log.error("配置热重载失败: %s", e)

    # ---- 生命周期 ----
    def run(self) -> None:
        log.info("启动 MediaMaid 闭环守护进程…")
        self.watcher.start_background()

        if self.sub.subscribers:
            threading.Thread(target=self._subscribe_loop, daemon=True).start()
            log.info("订阅轮询已启动（每 %ds）", self.config.subscribe_interval)
        else:
            log.info("未配置订阅器，跳过订阅轮询")

        # 完成轮询线程常驻，内部按 poll_completed 决定是否真正轮询（支持热开关）
        threading.Thread(target=self._completion_loop, daemon=True).start()
        if self.config.poll_completed:
            log.info("下载完成轮询已启动（每 %ds）", self.config.poll_interval)

        threading.Thread(target=self._config_watch_loop, daemon=True).start()

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
