"""订阅→下载 流程：按订阅条目发现 Release → 去重 → 下载器提交 → 通知。

订阅器(rss 等)是类型；订阅(Subscription)是某类型的命名实例。一个 runner 遍历
config.subscriptions，对每条 enabled 订阅实例化其订阅器并抓取。
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from .config import Config, Subscription
from .logging_conf import get_logger
from .models import Event, Release
from .plugins import Downloader, Subscriber, close_plugins, create, load_plugins
from .store import StateStore

log = get_logger(__name__)


def build_subscriptions(config: Config) -> List[Tuple[Subscription, Subscriber]]:
    """为每条启用订阅实例化其订阅器，返回 (订阅, 订阅器实例) 列表。"""
    load_plugins()
    out: List[Tuple[Subscription, Subscriber]] = []
    for sub in config.enabled_subscriptions():
        try:
            inst = create("subscriber", sub.subscriber, sub.config)
        except Exception as e:  # noqa: BLE001
            log.error("订阅 %s 加载订阅器 %s 失败: %s", sub.name, sub.subscriber, e)
            continue
        out.append((sub, inst))
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
        self.store = store
        self._notify = notify or (lambda e: None)
        self.reload(config)

    def reload(self, config: Config) -> None:
        """用新配置重建订阅/下载器（热重载用）。"""
        # 先关闭旧实例，避免下载器会话/连接泄漏
        close_plugins(s for _, s in getattr(self, "subs", []))
        close_plugins(getattr(self, "downloaders", None))
        self.config = config
        self.subs = build_subscriptions(config)
        self.downloaders = build_downloaders(config)

    # 兼容旧属性名（部分测试/代码读 subscribers）
    @property
    def subscribers(self) -> List[Subscriber]:
        return [inst for _, inst in self.subs]

    def run_once(self) -> int:
        """跑一轮：所有启用订阅各自抓取→去重→下载。返回新提交下载数。"""
        if not self.subs:
            log.warning("未配置订阅")
            return 0
        if not self.downloaders:
            log.warning("未配置下载器，新资源只记录不下载")

        submitted = 0
        for sub, inst in self.subs:
            try:
                releases = inst.fetch()
            except Exception as e:  # noqa: BLE001
                log.error("订阅 %s 抓取失败: %s", sub.name, e)
                continue
            for rel in releases:
                if self.store.release_seen(rel.guid):
                    continue
                self.store.mark_release(rel.guid, rel.title, sub.id)
                if self._dispatch(rel):
                    submitted += 1
        log.info("订阅本轮新提交 %d 个下载", submitted)
        return submitted

    def _dispatch(self, rel) -> bool:
        for dl in self.downloaders:
            if dl.add(rel):
                self._notify(Event("download_added", f"已提交下载: {rel.title}"))
                return True
        return False

    def preview(self, subscription: Subscription) -> List[Release]:
        """抓取某条订阅当前可见资源（不去重、不下载）。"""
        try:
            inst = create("subscriber", subscription.subscriber, subscription.config)
            return inst.fetch()
        except Exception as e:  # noqa: BLE001
            log.error("订阅 %s 预览失败: %s", subscription.name, e)
            return []

    def download_release(self, rel: Release, sub_id: Optional[str] = None) -> bool:
        """手动下载单条资源：提交成功则标记已处理。"""
        ok = self._dispatch(rel)
        if ok:
            self.store.mark_release(rel.guid, rel.title, sub_id)
        return ok

    def run_loop(self, interval: int) -> None:
        log.info("订阅守护启动，每 %ds 一轮（Ctrl-C 退出）", interval)
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("收到中断，停止订阅守护")
