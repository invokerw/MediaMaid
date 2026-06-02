"""空刮削器：不查询元数据，仅按文件名整理时的兜底。"""

from __future__ import annotations

from typing import Optional

from ...models import MediaInfo, MediaItem
from ..base import Scraper
from ..registry import register


@register
class NoScrapeScraper(Scraper):
    name = "noscrape"
    description = "不查询元数据，仅按文件名整理时的内部兜底"
    hidden = True  # 内部兜底，不在 Web 插件页展示

    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        return None
