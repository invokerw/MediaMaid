"""刮削器插件子包，并提供标题匹配打分工具。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional


def _norm(s: str) -> str:
    """归一化标题：小写、去标点（中英通用）、压缩空白。"""
    s = s.lower()
    # 把标点（含中文标点）替换为空格，保留中英文与数字
    s = re.sub(r"[^\w一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str, b: str) -> float:
    """两个标题的相似度 0~1（忽略大小写、标点与多余空白）。

    在序列相似度基础上，对"一方完全包含另一方"给加权——
    处理"标题 + 副标题/年份/字幕组"导致的长度差异（如 "遮天" vs "遮天 第一季"）。
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    shorter, longer = sorted((na, nb), key=len)
    # 子串包含：短串是长串的完整词组前缀/子串时给高分（按长度比例，避免过短误命中）
    if shorter in longer and len(shorter) >= 2:
        contain = 0.6 + 0.4 * (len(shorter) / len(longer))
        return max(ratio, contain)
    return ratio


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
