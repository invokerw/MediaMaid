"""TMDB 刮削器：电影 + 剧集，带结果缓存。"""

from __future__ import annotations

from typing import Optional

import httpx

from ..logging_conf import get_logger
from ..models import MediaInfo, MediaItem, MediaType
from .base import Scraper, score_match

log = get_logger(__name__)

_BASE = "https://api.themoviedb.org/3"
_IMG = "https://image.tmdb.org/t/p/original"


class TMDBScraper(Scraper):
    def __init__(
        self,
        api_key: str,
        language: str = "zh-CN",
        min_confidence: float = 0.5,
        timeout: float = 15.0,
    ):
        self.api_key = api_key
        self.language = language
        self.min_confidence = min_confidence
        self.client = httpx.Client(timeout=timeout)
        # 进程内缓存：避免同一剧集多集重复搜索
        self._search_cache: dict = {}

    def _get(self, path: str, **params) -> Optional[dict]:
        params.setdefault("api_key", self.api_key)
        params.setdefault("language", self.language)
        try:
            resp = self.client.get(f"{_BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            log.warning("TMDB 请求失败 %s: %s", path, e)
            return None

    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        if item.media_type == MediaType.MOVIE:
            return self._scrape_movie(item)
        if item.media_type == MediaType.EPISODE:
            return self._scrape_episode(item)
        return None

    # ---- 电影 ----
    def _scrape_movie(self, item: MediaItem) -> Optional[MediaInfo]:
        key = ("movie", item.title, item.year)
        results = self._search_cache.get(key)
        if results is None:
            params = {"query": item.title}
            if item.year:
                params["year"] = item.year
            data = self._get("/search/movie", **params) or {}
            results = data.get("results", [])
            self._search_cache[key] = results
        if not results:
            return None

        best, conf = self._best(results, item, title_key="title", date_key="release_date")
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
        key = ("tv", item.title, item.year)
        results = self._search_cache.get(key)
        if results is None:
            params = {"query": item.title}
            if item.year:
                params["first_air_date_year"] = item.year
            data = self._get("/search/tv", **params) or {}
            results = data.get("results", [])
            self._search_cache[key] = results
        if not results:
            return None

        best, conf = self._best(results, item, title_key="name", date_key="first_air_date")
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

    def _best(self, results, item: MediaItem, title_key: str, date_key: str):
        best, best_conf = None, -1.0
        for r in results:
            conf = score_match(
                item.title, item.year, r.get(title_key, ""), _year_of(r.get(date_key))
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
