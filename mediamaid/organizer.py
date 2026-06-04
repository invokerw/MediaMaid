"""落地：把 MediaItem 渲染为目标路径并执行传输，写 nfo/封面。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from . import naming, nfo, transfer
from .config import Config
from .logging_conf import get_logger
from .models import MediaInfo, MediaItem, MediaType, TransferPlan

log = get_logger(__name__)


class Organizer:
    def __init__(self, config: Config):
        self.config = config
        self._http: Optional[httpx.Client] = None

    def _client(self) -> httpx.Client:
        """惰性创建并复用图片下载用的 HTTP 连接（避免每张图新建连接）。"""
        if self._http is None:
            self._http = httpx.Client(timeout=30.0)
        return self._http

    def close(self) -> None:
        """释放持有的资源（图片下载用的 HTTP 连接等）。"""
        if self._http is not None:
            try:
                self._http.close()
            except Exception:  # noqa: BLE001 - 关闭尽力而为
                pass
            self._http = None

    # TMDB 题材 ID：16=动画
    _ANIME_GENRE_ID = 16

    def _category(self, item: MediaItem, info: Optional[MediaInfo]) -> str:
        """分类（tv/anime）：显式指定（绑定规则/手动）优先；否则按 TMDB 题材判定。

        借鉴 nas-tools：刮削结果题材含「动画」(genre 16) 即归为动漫。
        """
        if item.category:
            return item.category
        if info and self._ANIME_GENRE_ID in (info.genre_ids or []):
            return "anime"
        return "tv"

    def plan(self, item: MediaItem, info: Optional[MediaInfo]) -> TransferPlan:
        rel = naming.render_dest(item, info, self.config.naming, self._category(item, info))
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
                if plan.item.media_type == MediaType.EPISODE:
                    nfo.write_tvshow_nfo(written.parent.parent, plan.info)
            if self.config.download_artwork:
                nfo.download_artwork(
                    written, plan.info, plan.item.media_type, client=self._client()
                )
        return written
