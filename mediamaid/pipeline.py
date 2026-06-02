"""串联四级流水线：识别 → 刮削 → 落地，并写状态库。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .identify import Identifier
from .logging_conf import get_logger
from .models import Event, MediaInfo, MediaItem, MediaType
from .organizer import Organizer
from .plugins import MediaServer, Notifier, Scraper, close_plugins, create, load_plugins
from .store import StateStore

log = get_logger(__name__)


@dataclass
class Result:
    item: MediaItem
    status: str  # done / skipped / failed / unmatched
    dest: Optional[Path] = None
    error: Optional[str] = None


def build_scrapers(config: Config) -> List[Scraper]:
    """按配置加载启用的刮削器插件；为空则用 noscrape 兜底。"""
    load_plugins()
    scrapers: List[Scraper] = []
    for spec in config.plugin_specs("scraper"):
        try:
            scrapers.append(create("scraper", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载刮削器 %s 失败: %s", spec.name, e)
    if not scrapers:
        log.warning("未配置刮削器，降级为仅按文件名整理（不刮削）")
        scrapers.append(create("scraper", "noscrape"))
    return scrapers


def build_notifiers(config: Config) -> List[Notifier]:
    load_plugins()
    notifiers: List[Notifier] = []
    for spec in config.plugin_specs("notifier"):
        try:
            notifiers.append(create("notifier", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载通知器 %s 失败: %s", spec.name, e)
    return notifiers


def build_mediaservers(config: Config) -> List[MediaServer]:
    load_plugins()
    servers: List[MediaServer] = []
    for spec in config.plugin_specs("mediaserver"):
        try:
            servers.append(create("mediaserver", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载媒体服务器 %s 失败: %s", spec.name, e)
    return servers


class Pipeline:
    def __init__(self, config: Config, store: Optional[StateStore] = None):
        self.store = store
        # 按源文件粒度的串行锁：防止 watcher 与完成轮询两线程并发整理同一文件
        # （重复硬链接/重命名）。不同文件用不同锁，故不影响并行扫描。
        self._claim_locks: Dict[str, threading.Lock] = {}
        self._claim_guard = threading.Lock()
        self.reload(config)

    def _claim_lock(self, src: Path) -> threading.Lock:
        key = str(src)
        with self._claim_guard:
            lk = self._claim_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._claim_locks[key] = lk
            return lk

    def reload(self, config: Config) -> None:
        """用新配置重建标识器/刮削器/通知器/整理器（热重载用，store 不变）。"""
        # 先关闭旧插件实例，避免 HTTP 连接/fd 泄漏
        close_plugins(getattr(self, "scrapers", None))
        close_plugins(getattr(self, "notifiers", None))
        close_plugins(getattr(self, "mediaservers", None))
        if getattr(self, "organizer", None) is not None:
            self.organizer.close()
        self.config = config
        self.identifier = Identifier(config)
        self.scrapers = build_scrapers(config)
        self.notifiers = build_notifiers(config)
        self.mediaservers = build_mediaservers(config)
        self.organizer = Organizer(config)

    def refresh_media_servers(self) -> None:
        """通知所有媒体服务器刷新库（异常不致命）。整理完一批后调用。"""
        for ms in self.mediaservers:
            try:
                ms.refresh()
            except Exception as e:  # noqa: BLE001
                log.warning("媒体服务器 %s 刷新失败: %s", ms.name, e)

    def _scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        """链式刮削：依次尝试各刮削器，返回首个命中的结果。"""
        for scraper in self.scrapers:
            try:
                info = scraper.scrape(item)
            except Exception as e:  # noqa: BLE001
                log.warning("刮削器 %s 异常 %s: %s", scraper.name, item.source.name, e)
                continue
            if info is not None:
                return info
        return None

    def notify(self, event: Event) -> None:
        for n in self.notifiers:
            try:
                n.notify(event)
            except Exception as e:  # noqa: BLE001
                log.warning("通知器 %s 失败: %s", n.name, e)

    def process_item(
        self, item: MediaItem, dry_run: bool = False, batch_id: Optional[str] = None
    ) -> Result:
        if item.media_type == MediaType.UNKNOWN:
            log.warning("未知媒体类型，跳过: %s", item.source.name)
            return Result(item, "skipped", error="unknown type")

        # 非 dry-run 且有状态库时，对该源文件串行化：检查去重→落地→记录 一气呵成，
        # 避免并发线程对同一文件重复整理。
        if self.store and not dry_run:
            with self._claim_lock(item.source):
                return self._process_locked(item, batch_id)
        return self._process_unlocked(item, dry_run, batch_id)

    def _process_locked(self, item: MediaItem, batch_id: Optional[str]) -> Result:
        if self.store.is_done(item.source):
            log.debug("已处理过，跳过: %s", item.source.name)
            return Result(item, "skipped", error="already done")
        return self._process_unlocked(item, False, batch_id)

    def _process_unlocked(
        self, item: MediaItem, dry_run: bool, batch_id: Optional[str]
    ) -> Result:
        # 刮削（失败不致命，降级为仅文件名）
        info = self._scrape(item)

        try:
            plan = self.organizer.plan(item, info)
            dest = self.organizer.execute(plan, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            log.error("落地失败 %s: %s", item.source.name, e)
            if self.store and not dry_run:
                self.store.record(
                    item.source, None, self.config.action.value, "failed", str(e), batch_id
                )
            if not dry_run:
                self.notify(Event("error", f"落地失败: {item.source.name}: {e}", item=item))
            return Result(item, "failed", error=str(e))

        if dest is None:
            return Result(item, "skipped", error="conflict skip")

        if self.store and not dry_run:
            self.store.record(item.source, dest, plan.action.value, "done", batch_id=batch_id)
        if not dry_run:
            self.notify(Event("organized", f"已整理: {dest.name}", item=item, info=info, dest=dest))
        return Result(item, "done", dest=dest)

    def process_path(
        self, path: Path, dry_run: bool = False, batch_id: Optional[str] = None
    ) -> Optional[Result]:
        """处理单个文件路径（供 watcher 调用）。"""
        path = Path(path)
        if not self.identifier.accept_file(path):
            return None
        item = self.identifier.identify(path)
        if item is None:
            return None
        if batch_id is None and self.store and not dry_run:
            batch_id = self.store.new_batch_id()
        return self.process_item(item, dry_run=dry_run, batch_id=batch_id)

    def process_target(self, path: Path, dry_run: bool = False) -> List[Result]:
        """处理一个文件或目录目标（供下载完成轮询用）。

        目录（多文件种子）→ 扫描其中候选文件逐个处理；文件 → 单个处理。
        同一目标内的多文件共享一个 batch_id，便于按批 undo。
        """
        path = Path(path)
        batch_id = self.store.new_batch_id() if (self.store and not dry_run) else None
        if path.is_dir():
            results = [
                self.process_item(it, dry_run=dry_run, batch_id=batch_id)
                for it in self.identifier.scan_dir(path)
            ]
        else:
            result = self.process_path(path, dry_run=dry_run, batch_id=batch_id)
            results = [result] if result is not None else []
        if not dry_run and any(r and r.status == "done" for r in results):
            self.refresh_media_servers()
        return results

    def scan(self, dry_run: bool = False) -> List[Result]:
        """全量扫描所有源目录并处理。

        scan_workers>1 时用有界线程池并行（瓶颈是 TMDB 网络请求）；
        process_item 本身线程安全（按源文件串行 + thread-local DB 连接）。
        """
        items = self.identifier.scan_dirs(self.config.source_dirs)
        log.info("识别到 %d 个候选文件", len(items))
        batch_id = self.store.new_batch_id() if (self.store and not dry_run) else None

        workers = max(1, self.config.scan_workers)
        if workers == 1 or len(items) <= 1:
            results = [self.process_item(it, dry_run=dry_run, batch_id=batch_id) for it in items]
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
                results = list(
                    pool.map(
                        lambda it: self.process_item(it, dry_run=dry_run, batch_id=batch_id),
                        items,
                    )
                )
        done = sum(1 for r in results if r.status == "done")
        log.info("完成: %d done / %d 总数", done, len(results))
        if not dry_run and done:
            self.refresh_media_servers()
        return results
