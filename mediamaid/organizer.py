"""落地：把 MediaItem 渲染为目标路径并执行传输，写 nfo/封面。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import naming, nfo, transfer
from .config import Config
from .logging_conf import get_logger
from .models import MediaInfo, MediaItem, TransferPlan

log = get_logger(__name__)


class Organizer:
    def __init__(self, config: Config):
        self.config = config

    def _category(self, item: MediaItem) -> str:
        """按 anime_keywords 命中源路径则归为动漫，否则普通剧集。"""
        src = str(item.source).lower()
        if any(k.lower() in src for k in self.config.anime_keywords if k):
            return "anime"
        return "tv"

    def plan(self, item: MediaItem, info: Optional[MediaInfo]) -> TransferPlan:
        rel = naming.render_dest(item, info, self.config.naming, self._category(item))
        dest = self.config.library_dir / rel
        return TransferPlan(
            item=item,
            info=info,
            source=item.source,
            dest=dest,
            action=self.config.action,
        )

    def execute(self, plan: TransferPlan, dry_run: bool = False) -> Optional[Path]:
        """执行传输，返回实际落地路径（跳过返回 None）。"""
        written = transfer.transfer(
            plan.source,
            plan.dest,
            plan.action,
            on_conflict=self.config.on_conflict,
            dry_run=dry_run,
        )
        if written is None or dry_run:
            return written

        # 刮削附加产物
        if plan.info is not None:
            if self.config.write_nfo:
                nfo.write_nfo(written, plan.info, plan.item.media_type)
            if self.config.download_artwork:
                nfo.download_artwork(written, plan.info, plan.item.media_type)
        return written
