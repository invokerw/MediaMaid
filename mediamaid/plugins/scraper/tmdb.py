"""TMDB 刮削器插件：电影 + 剧集，带进程内缓存与置信度匹配。"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Optional

import httpx
from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import MediaInfo, MediaItem, MediaType
from ..base import Scraper
from ..registry import register
from . import score_match

log = get_logger(__name__)

_BASE = "https://api.themoviedb.org/3"
_IMG = "https://image.tmdb.org/t/p/original"


class _TTLCache:
    """容量上限 + TTL 的简易 LRU 缓存（线程安全）。

    只缓存"成功的搜索"，瞬时失败不应进缓存。并行扫描时多线程共享同一刮削器
    实例，故用锁保护。
    """

    def __init__(self, maxsize: int = 512, ttl: float = 3600.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[tuple, tuple]" = OrderedDict()  # key -> (value, expire_at)
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expire_at = item
            if time.monotonic() >= expire_at:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)  # LRU 触达
            return value

    def set(self, key, value) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + self.ttl)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)  # 淘汰最久未用


class TMDBConfig(BaseModel):
    api_key: str
    language: str = "zh-CN"
    min_confidence: float = 0.5
    timeout: float = 15.0
    # 搜索结果进程内缓存：容量上限与存活秒数（避免无界增长 / 元数据永不刷新）
    cache_max: int = 512
    cache_ttl: float = 3600.0


@register
class TMDBScraper(Scraper):
    name = "tmdb"
    ConfigModel = TMDBConfig

    def __init__(self, config: TMDBConfig):
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)
        # 进程内缓存：避免同一剧集多集重复搜索（有上限 + TTL）
        self._search_cache = _TTLCache(maxsize=config.cache_max, ttl=config.cache_ttl)

    @property
    def min_confidence(self) -> float:
        return self.config.min_confidence

    def close(self) -> None:
        """释放底层 HTTP 连接（热重载替换旧实例时调用）。"""
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - 关闭尽力而为
            pass

    def _get(self, path: str, **params) -> Optional[dict]:
        params.setdefault("api_key", self.config.api_key)
        params.setdefault("language", self.config.language)
        try:
            resp = self.client.get(f"{_BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            log.warning("TMDB 请求失败 %s: %s", path, e)
            return None

    def _search(self, kind: str, item: MediaItem) -> Optional[list]:
        """搜索 TMDB 并缓存。返回结果列表（可能为空表示"确无匹配"）；

        返回 None 表示请求失败——失败不进缓存，下次仍会重试（避免瞬时失败投毒）。
        """
        key = (kind, item.title, item.year)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached

        params = {"query": item.title}
        if item.year:
            params["year" if kind == "movie" else "first_air_date_year"] = item.year
        data = self._get(f"/search/{kind}", **params)
        if data is None:
            return None  # 瞬时失败：不缓存
        results = data.get("results", [])
        self._search_cache.set(key, results)  # 成功（含空结果）才缓存
        return results

    def test(self):
        data = self._get("/configuration")
        if data and "images" in data:
            return True, "TMDB API key 有效"
        return False, "TMDB 连接失败：请检查 API key 或网络"

    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        if item.media_type == MediaType.MOVIE:
            return self._scrape_movie(item)
        if item.media_type == MediaType.EPISODE:
            return self._scrape_episode(item)
        return None

    # ---- 电影 ----
    def _scrape_movie(self, item: MediaItem) -> Optional[MediaInfo]:
        results = self._search("movie", item)
        if not results:
            return None

        best, conf = self._best(
            results, item, title_key="title", orig_key="original_title", date_key="release_date"
        )
        if best is None or conf < self.min_confidence:
            log.info("电影匹配置信度不足(%.2f): %s", conf, item.title)
            return None

        year = _year_of(best.get("release_date"))
        return MediaInfo(
            title=best.get("title") or item.title,
            year=year,
            tmdb_id=best.get("id"),
            overview=best.get("overview"),
            poster_url=_img(best.get("poster_path")),
            fanart_url=_img(best.get("backdrop_path")),
            confidence=conf,
        )

    # ---- 剧集 ----
    def _scrape_episode(self, item: MediaItem) -> Optional[MediaInfo]:
        results = self._search("tv", item)
        if not results:
            return None

        best, conf = self._best(
            results, item, title_key="name", orig_key="original_name", date_key="first_air_date"
        )
        if best is None or conf < self.min_confidence:
            log.info("剧集匹配置信度不足(%.2f): %s", conf, item.title)
            return None

        show_id = best.get("id")
        show_year = _year_of(best.get("first_air_date"))
        info = MediaInfo(
            title=best.get("name") or item.title,
            year=show_year,
            tmdb_id=show_id,
            overview=best.get("overview"),
            poster_url=_img(best.get("poster_path")),
            fanart_url=_img(best.get("backdrop_path")),
            season=item.season,
            episode=item.episode,
            confidence=conf,
        )
        # 拉取单集标题
        if show_id and item.season is not None and item.episode is not None:
            ep = self._get(f"/tv/{show_id}/season/{item.season}/episode/{item.episode}")
            if ep:
                info.episode_title = ep.get("name")
        return info

    def _best(self, results, item: MediaItem, title_key: str, orig_key: str, date_key: str):
        """挑最佳匹配。同时比对本地化标题与原始标题(取较高分)，

        因为 language=zh-CN 时 title 是中文译名，英文解析名应与 original_title 匹配。
        """
        best, best_conf = None, -1.0
        for r in results:
            year = _year_of(r.get(date_key))
            conf = max(
                score_match(item.title, item.year, r.get(title_key, ""), year),
                score_match(item.title, item.year, r.get(orig_key, ""), year),
            )
            if conf > best_conf:
                best, best_conf = r, conf
        return best, best_conf


def _year_of(date_str: Optional[str]) -> Optional[int]:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _img(path: Optional[str]) -> Optional[str]:
    return f"{_IMG}{path}" if path else None
