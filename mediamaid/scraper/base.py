"""刮削器抽象接口与置信度工具。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import Optional

from ..models import MediaInfo, MediaItem


def title_similarity(a: str, b: str) -> float:
    """两个标题的相似度 0~1（忽略大小写与多余空白）。"""
    norm = lambda s: re.sub(r"\s+", " ", s.lower()).strip()
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def score_match(
    query_title: str,
    query_year: Optional[int],
    result_title: str,
    result_year: Optional[int],
) -> float:
    """综合标题相似度与年份匹配，返回置信度 0~1。"""
    sim = title_similarity(query_title, result_title)
    if query_year and result_year:
        year_bonus = 0.15 if query_year == result_year else -0.25
    else:
        year_bonus = 0.0
    return max(0.0, min(1.0, sim + year_bonus))


class Scraper(ABC):
    """元数据源接口。便于扩展 TVDB / Bangumi 等。"""

    @abstractmethod
    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        """根据识别结果查询权威元数据；失败/无匹配返回 None。"""
        raise NotImplementedError


class NullScraper(Scraper):
    """不刮削，直接返回 None（仅按文件名整理）。"""

    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        return None
