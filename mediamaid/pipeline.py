"""串联四级流水线：识别 → 刮削 → 落地，并写状态库。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config import Config
from .identify import Identifier
from .logging_conf import get_logger
from .models import MediaItem, MediaType
from .organizer import Organizer
from .scraper import NullScraper, Scraper, TMDBScraper
from .store import StateStore

log = get_logger(__name__)


@dataclass
class Result:
    item: MediaItem
    status: str  # done / skipped / failed / unmatched
    dest: Optional[Path] = None
    error: Optional[str] = None


def build_scraper(config: Config) -> Scraper:
    sc = config.scraper
    if sc.enabled and sc.tmdb_api_key:
        return TMDBScraper(
            api_key=sc.tmdb_api_key,
            language=sc.language,
            min_confidence=sc.min_confidence,
        )
    if sc.enabled and not sc.tmdb_api_key:
        log.warning("未配置 tmdb_api_key，降级为仅按文件名整理（不刮削）")
    return NullScraper()


class Pipeline:
    def __init__(self, config: Config, store: Optional[StateStore] = None):
        self.config = config
        self.identifier = Identifier(config.filters)
        self.scraper = build_scraper(config)
        self.organizer = Organizer(config)
        self.store = store

    def process_item(self, item: MediaItem, dry_run: bool = False) -> Result:
        if item.media_type == MediaType.UNKNOWN:
            log.warning("未知媒体类型，跳过: %s", item.source.name)
            return Result(item, "skipped", error="unknown type")

        if self.store and not dry_run and self.store.is_done(item.source):
            log.debug("已处理过，跳过: %s", item.source.name)
            return Result(item, "skipped", error="already done")

        # 刮削（失败不致命，降级为仅文件名）
        info = None
        try:
            info = self.scraper.scrape(item)
        except Exception as e:  # noqa: BLE001
            log.warning("刮削异常，降级处理 %s: %s", item.source.name, e)

        try:
            plan = self.organizer.plan(item, info)
            dest = self.organizer.execute(plan, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            log.error("落地失败 %s: %s", item.source.name, e)
            if self.store and not dry_run:
                self.store.record(item.source, None, self.config.action.value, "failed", str(e))
            return Result(item, "failed", error=str(e))

        if dest is None:
            return Result(item, "skipped", error="conflict skip")

        if self.store and not dry_run:
            self.store.record(item.source, dest, plan.action.value, "done")
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
