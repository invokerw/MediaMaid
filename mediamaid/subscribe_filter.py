"""订阅资源的质量过滤与择优。

对任意订阅器产出的 Release 通用：先按规则过滤，再对"同一集"的多个候选择优保留一个。
集身份由解析器链从标题解析（复用 identify.Identifier）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .config import SubscriptionFilter
from .models import Release


def _size_mb(rel: Release) -> Optional[float]:
    return rel.size / (1024 * 1024) if rel.size else None


def passes(rel: Release, f: SubscriptionFilter) -> bool:
    """Release 是否通过过滤规则。"""
    title = rel.title.lower()
    if f.resolutions and not any(r.lower() in title for r in f.resolutions):
        return False
    if f.include_keywords and not all(k.lower() in title for k in f.include_keywords):
        return False
    if f.exclude_keywords and any(k.lower() in title for k in f.exclude_keywords):
        return False
    size = _size_mb(rel)
    if size is not None:
        if f.min_size_mb is not None and size < f.min_size_mb:
            return False
        if f.max_size_mb is not None and size > f.max_size_mb:
            return False
    return True


def score(rel: Release, f: SubscriptionFilter) -> Tuple[int, float]:
    """择优排序键（越大越优）。

    prefer 命中靠前者得分越高；其次按体积（通常体积大=质量高）。
    """
    title = rel.title.lower()
    prefer_score = 0
    n = len(f.prefer)
    for i, kw in enumerate(f.prefer):
        if kw.lower() in title:
            prefer_score = max(prefer_score, n - i)  # 越靠前权重越大
    return (prefer_score, _size_mb(rel) or 0.0)


def best_per_episode(
    releases: List[Release], identifier, f: Optional[SubscriptionFilter] = None
) -> List[Release]:
    """同一集的多个候选只保留 score 最高的一个。

    解析不出集号者（电影/整季包/无法识别）原样全部保留。
    identifier: 具备 parse_name(name) -> (ParseResult|None, parser_name) 的对象。
    """
    return _dedupe(releases, identifier, f or SubscriptionFilter())


def _dedupe(releases: List[Release], identifier, f: SubscriptionFilter) -> List[Release]:
    best: dict = {}
    passthrough: List[Release] = []
    for rel in releases:
        key = _episode_key(rel, identifier)
        if key is None:
            passthrough.append(rel)
            continue
        cur = best.get(key)
        if cur is None or score(rel, f) > score(cur, f):
            best[key] = rel
    return passthrough + list(best.values())


def _episode_key(rel: Release, identifier) -> Optional[Tuple[str, int, int]]:
    """从标题解析 (show, season, episode)；非剧集或解析失败返回 None。"""
    try:
        res, _ = identifier.parse_name(rel.title)
    except Exception:  # noqa: BLE001 - 解析异常视为无法定位集号
        return None
    if res is None or res.title is None:
        return None
    if res.season is None or res.episode is None:
        return None
    return (res.title.lower(), int(res.season), int(res.episode))


def filter_and_pick(
    releases: List[Release], f: SubscriptionFilter, identifier
) -> List[Release]:
    """过滤 + 同集择优，一步到位（runner 主入口）。"""
    kept = [r for r in releases if passes(r, f)]
    return _dedupe(kept, identifier, f)
