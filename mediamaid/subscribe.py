"""订阅→下载 流程：按订阅条目发现 Release → 去重 → 下载器提交 → 通知。

订阅器(rss 等)是类型；订阅(Subscription)是某类型的命名实例。一个 runner 遍历
config.subscriptions，对每条 enabled 订阅实例化其订阅器并抓取。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import subscribe_filter
from .config import Config, Subscription
from .identify import Identifier
from .logging_conf import get_logger
from .models import Event, MediaItem, Release
from .plugins import Downloader, MediaServer, Subscriber, close_plugins, create, load_plugins
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


def build_mediaservers(config: Config) -> List[MediaServer]:
    load_plugins()
    out: List[MediaServer] = []
    for spec in config.plugin_specs("mediaserver"):
        try:
            out.append(create("mediaserver", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载媒体服务器 %s 失败: %s", spec.name, e)
    return out


class SubscribeRunner:
    def __init__(self, config: Config, store: StateStore, notify=None):
        self.store = store
        self._notify = notify or (lambda e: None)
        self.reload(config)

    def reload(self, config: Config) -> None:
        """用新配置重建订阅/下载器/媒体服务器（热重载用）。"""
        # 先关闭旧实例，避免下载器会话/连接泄漏
        close_plugins(s for _, s in getattr(self, "subs", []))
        close_plugins(getattr(self, "downloaders", None))
        close_plugins(getattr(self, "mediaservers", None))
        self.config = config
        self.subs = build_subscriptions(config)
        self.downloaders = build_downloaders(config)
        self.mediaservers = build_mediaservers(config)
        # 复用识别器的解析器链，从 Release 标题解析集号（集数去重 / 择优）
        self.identifier = Identifier(config)

    # 兼容旧属性名（部分测试/代码读 subscribers）
    @property
    def subscribers(self) -> List[Subscriber]:
        return [inst for _, inst in self.subs]

    def run_once(self) -> int:
        """跑一轮：所有启用订阅各自抓取→过滤择优→去重→下载。返回新提交下载数。"""
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
            # 质量过滤 + 同集择优
            releases = subscribe_filter.filter_and_pick(
                releases, sub.filters, self.identifier
            )
            for rel in releases:
                submitted += self._consider(sub, rel)
        log.info("订阅本轮新提交 %d 个下载", submitted)
        return submitted

    def _consider(self, sub: Subscription, rel: Release) -> int:
        """对单条候选做去重判定并尝试下载，返回是否新提交(0/1)。"""
        if self.store.release_seen(rel.guid):
            return 0
        ep = self._episode_of(rel)
        # 集数去重：同一集已抓过（换源/重复）→ 记录已见后跳过
        if ep and self.store.episode_grabbed(sub.id, ep[0], ep[1], ep[2]):
            self.store.mark_release(rel.guid, rel.title, sub.id)
            log.debug("集已抓过，跳过: %s", rel.title)
            return 0
        # 已拥有去重：媒体服务器库中已有 → 跳过
        if sub.skip_existing and self._already_owned(rel, ep):
            self.store.mark_release(rel.guid, rel.title, sub.id)
            log.debug("媒体库已有，跳过: %s", rel.title)
            return 0
        self.store.mark_release(rel.guid, rel.title, sub.id)
        if self._dispatch(rel):
            if ep:
                self.store.mark_episode(sub.id, ep[0], ep[1], ep[2], rel.guid)
            return 1
        return 0

    def _episode_of(self, rel: Release):
        """解析 Release 标题得到 (show_key, season, episode)，非剧集/失败返回 None。"""
        try:
            res, _ = self.identifier.parse_name(rel.title)
        except Exception:  # noqa: BLE001
            return None
        if res is None or not res.title or res.season is None or res.episode is None:
            return None
        return (res.title, int(res.season), int(res.episode))

    def _already_owned(self, rel: Release, ep) -> bool:
        """查媒体服务器是否已拥有该资源（best-effort）。"""
        if not self.mediaservers:
            return False
        try:
            res, _ = self.identifier.parse_name(rel.title)
        except Exception:  # noqa: BLE001
            return False
        if res is None or not res.title:
            return False
        item = MediaItem(
            source=Path(rel.title),
            media_type=res.type,
            title=res.title,
            year=res.year,
            season=res.season,
            episode=res.episode,
        )
        for ms in self.mediaservers:
            try:
                if ms.exists(item, None):
                    return True
            except Exception as e:  # noqa: BLE001
                log.warning("媒体服务器 %s 查询失败: %s", ms.name, e)
        return False

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
        """手动下载单条资源：提交成功则标记已处理（含集数进度）。"""
        ok = self._dispatch(rel)
        if ok:
            self.store.mark_release(rel.guid, rel.title, sub_id)
            ep = self._episode_of(rel)
            if ep and sub_id:
                self.store.mark_episode(sub_id, ep[0], ep[1], ep[2], rel.guid)
        return ok

    def run_loop(self, interval: int) -> None:
        log.info("订阅守护启动，每 %ds 一轮（Ctrl-C 退出）", interval)
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("收到中断，停止订阅守护")
