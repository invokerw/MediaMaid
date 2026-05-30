"""刮削器插件子包，并提供标题匹配打分工具。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional


def title_similarity(a: str, b: str) -> float:
    """两个标题的相似度 0~1（忽略大小写与多余空白）。"""
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower()).strip()

    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def score_match(
    query_title: str,
    query_year: Optional[int],
    result_title: str,
    result_year: Optional[int],
) -> float:
    """综合标题相似度与年份匹配，返回置信度 0~1。"""
    if not result_title:
        return 0.0
    sim = title_similarity(query_title, result_title)
    if query_year and result_year:
        year_bonus = 0.15 if query_year == result_year else -0.25
    else:
        year_bonus = 0.0
    return max(0.0, min(1.0, sim + year_bonus))
