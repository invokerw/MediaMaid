"""订阅→下载 流程：订阅器发现 Release → 去重 → 下载器提交 → 通知。"""

from __future__ import annotations

import time
from typing import List

from .config import Config
from .logging_conf import get_logger
from .models import Event
from .plugins import Downloader, Subscriber, create, load_plugins
from .store import StateStore

log = get_logger(__name__)


def build_subscribers(config: Config) -> List[Subscriber]:
    load_plugins()
    out: List[Subscriber] = []
    for spec in config.plugin_specs("subscriber"):
        try:
            out.append(create("subscriber", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载订阅器 %s 失败: %s", spec.name, e)
    return out


def build_downloaders(config: Config) -> List[Downloader]:
    load_plugins()
    out: List[Downloader] = []
    for spec in config.plugin_specs("downloader"):
        try:
            out.append(create("downloader", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载下载器 %s 失败: %s", spec.name, e)
    return out


class SubscribeRunner:
    def __init__(self, config: Config, store: StateStore, notify=None):
        self.config = config
        self.store = store
        self.subscribers = build_subscribers(config)
        self.downloaders = build_downloaders(config)
        self._notify = notify or (lambda e: None)

    def run_once(self) -> int:
        """跑一轮：返回本轮新提交下载的数量。"""
        if not self.subscribers:
            log.warning("未配置订阅器")
            return 0
        if not self.downloaders:
            log.warning("未配置下载器，新资源只记录不下载")

        submitted = 0
        for sub in self.subscribers:
            try:
                releases = sub.fetch()
            except Exception as e:  # noqa: BLE001
                log.error("订阅器 %s 抓取失败: %s", sub.name, e)
                continue
            for rel in releases:
                if self.store.release_seen(rel.guid):
                    continue
                self.store.mark_release(rel.guid, rel.title)
                if self._dispatch(rel):
                    submitted += 1
        log.info("订阅本轮新提交 %d 个下载", submitted)
        return submitted

    def _dispatch(self, rel) -> bool:
        # 交给首个能成功提交的下载器
        for dl in self.downloaders:
            if dl.add(rel):
                self._notify(Event("download_added", f"已提交下载: {rel.title}"))
                return True
        return False

    def run_loop(self, interval: int) -> None:
        log.info("订阅守护启动，每 %ds 一轮（Ctrl-C 退出）", interval)
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("收到中断，停止订阅守护")
