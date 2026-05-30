"""串联四级流水线：识别 → 刮削 → 落地，并写状态库。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config import Config
from .identify import Identifier
from .logging_conf import get_logger
from .models import Event, MediaInfo, MediaItem, MediaType
from .organizer import Organizer
from .plugins import Notifier, Scraper, create, load_plugins
from .store import StateStore

log = get_logger(__name__)


@dataclass
class Result:
    item: MediaItem
    status: str  # done / skipped / failed / unmatched
    dest: Optional[Path] = None
    error: Optional[str] = None


def build_scrapers(config: Config) -> List[Scraper]:
    """按配置加载启用的刮削器插件；为空则用 null 兜底。"""
    load_plugins()
    scrapers: List[Scraper] = []
    for spec in config.plugin_specs("scraper"):
        try:
            scrapers.append(create("scraper", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载刮削器 %s 失败: %s", spec.name, e)
    if not scrapers:
        log.warning("未配置刮削器，降级为仅按文件名整理（不刮削）")
        scrapers.append(create("scraper", "null"))
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


class Pipeline:
    def __init__(self, config: Config, store: Optional[StateStore] = None):
        self.config = config
        self.identifier = Identifier(config.filters)
        self.scrapers = build_scrapers(config)
        self.notifiers = build_notifiers(config)
        self.organizer = Organizer(config)
        self.store = store

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

    def process_item(self, item: MediaItem, dry_run: bool = False) -> Result:
        if item.media_type == MediaType.UNKNOWN:
            log.warning("未知媒体类型，跳过: %s", item.source.name)
            return Result(item, "skipped", error="unknown type")

        if self.store and not dry_run and self.store.is_done(item.source):
            log.debug("已处理过，跳过: %s", item.source.name)
            return Result(item, "skipped", error="already done")

        # 刮削（失败不致命，降级为仅文件名）
        info = self._scrape(item)

        try:
            plan = self.organizer.plan(item, info)
            dest = self.organizer.execute(plan, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            log.error("落地失败 %s: %s", item.source.name, e)
            if self.store and not dry_run:
                self.store.record(item.source, None, self.config.action.value, "failed", str(e))
            if not dry_run:
                self.notify(Event("error", f"落地失败: {item.source.name}: {e}", item=item))
            return Result(item, "failed", error=str(e))

        if dest is None:
            return Result(item, "skipped", error="conflict skip")

        if self.store and not dry_run:
            self.store.record(item.source, dest, plan.action.value, "done")
        if not dry_run:
            self.notify(Event("organized", f"已整理: {dest.name}", item=item, info=info, dest=dest))
        return Result(item, "done", dest=dest)

    def process_path(self, path: Path, dry_run: bool = False) -> Optional[Result]:
        """处理单个文件路径（供 watcher 调用）。"""
        path = Path(path)
        if not self.identifier.accept_file(path):
            return None
        item = self.identifier.identify(path)
        if item is None:
            return None
        return self.process_item(item, dry_run=dry_run)

    def scan(self, dry_run: bool = False) -> List[Result]:
        """全量扫描所有源目录并处理。"""
        items = self.identifier.scan_dirs(self.config.source_dirs)
        log.info("识别到 %d 个候选文件", len(items))
        results = [self.process_item(it, dry_run=dry_run) for it in items]
        done = sum(1 for r in results if r.status == "done")
        log.info("完成: %d done / %d 总数", done, len(results))
        return results
