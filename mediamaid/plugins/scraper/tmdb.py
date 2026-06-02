"""TMDB 刮削器插件：电影 + 剧集，带进程内缓存与置信度匹配。"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path
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

    可选 path：开启后写穿到 JSON 文件，进程重启后仍可命中（按墙钟过期）。
    内存过期判定仍用 monotonic（不受系统时钟回拨影响），持久化用墙钟。
    """

    def __init__(self, maxsize: int = 512, ttl: float = 3600.0, path=None):
        self.maxsize = maxsize
        self.ttl = ttl
        self.path = Path(path) if path else None
        # key -> (value, mono_expire, wall_expire)
        self._data: "OrderedDict[tuple, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        if self.path:
            self._load()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, mono_expire = item[0], item[1]
            if time.monotonic() >= mono_expire:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)  # LRU 触达
            return value

    def set(self, key, value) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + self.ttl, time.time() + self.ttl)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)  # 淘汰最久未用
            if self.path:
                self._persist_locked()

    # ---- 持久化（JSON 写穿）----
    def _persist_locked(self) -> None:
        try:
            rows = [[list(k), v, wall] for k, (v, _m, wall) in self._data.items()]
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(rows), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as e:  # noqa: BLE001 - 持久化失败不影响主流程
            log.debug("TMDB 缓存写盘失败: %s", e)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log.debug("TMDB 缓存读取失败: %s", e)
            return
        now = time.time()
        for key_list, value, wall in rows:
            if wall <= now:
                continue  # 已过期
            remaining = wall - now
            self._data[tuple(key_list)] = (value, time.monotonic() + remaining, wall)


class TMDBConfig(BaseModel):
    api_key: str
    language: str = "zh-CN"
    min_confidence: float = 0.5
    timeout: float = 15.0
    # 搜索结果进程内缓存：容量上限与存活秒数（避免无界增长 / 元数据永不刷新）
    cache_max: int = 512
    cache_ttl: float = 3600.0
    # 可选：缓存持久化到该 JSON 文件路径，进程重启后仍可命中（留空则仅进程内）
    cache_path: Optional[str] = None


@register
class TMDBScraper(Scraper):
    name = "tmdb"
    description = "TMDB 刮削器，匹配电影/剧集元数据，含进程内缓存与置信度评分"
    ConfigModel = TMDBConfig

    def __init__(self, config: TMDBConfig):
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)
        # 缓存：避免同一剧集多集重复搜索/拉详情（有上限 + TTL，可选落盘持久化）
        self._search_cache = _TTLCache(
            maxsize=config.cache_max, ttl=config.cache_ttl, path=config.cache_path
        )

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

    def _details(self, kind: str, tmdb_id: int) -> Optional[dict]:
        """拉取影片/剧集详情（含 genres + external_ids），带缓存。

        append_to_response=external_ids 让 genres 与 imdb/tvdb id 一次请求拿全。
        """
        key = ("details", kind, tmdb_id)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached
        data = self._get(f"/{kind}/{tmdb_id}", append_to_response="external_ids")
        if data is None:
            return None
        self._search_cache.set(key, data)
        return data

    def _season(self, show_id: int, season: int) -> Optional[dict]:
        """一次拉取整季（含所有单集），带缓存——整季多集只需一次请求。"""
        key = ("season", show_id, season)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached
        data = self._get(f"/tv/{show_id}/season/{season}")
        if data is None:
            return None
        self._search_cache.set(key, data)
        return data

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
        info = MediaInfo(
            title=best.get("title") or item.title,
            year=year,
            tmdb_id=best.get("id"),
            overview=best.get("overview"),
            poster_url=_img(best.get("poster_path")),
            fanart_url=_img(best.get("backdrop_path")),
            rating=best.get("vote_average") or None,
            confidence=conf,
        )
        # 拉详情补 genres + imdb id（提升 Jellyfin/Emby 匹配）
        if info.tmdb_id:
            details = self._details("movie", info.tmdb_id)
            if details:
                info.genres = [g.get("name") for g in details.get("genres", []) if g.get("name")]
                info.imdb_id = (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id")
        return info

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
        # 拉剧集详情补 genres + imdb/tvdb id
        if show_id:
            details = self._details("tv", show_id)
            if details:
                info.genres = [g.get("name") for g in details.get("genres", []) if g.get("name")]
                ext = details.get("external_ids") or {}
                info.imdb_id = ext.get("imdb_id")
                info.tvdb_id = ext.get("tvdb_id")
        # 整季拉取一次，从中取单集标题（整季多集省去逐集请求）
        if show_id and item.season is not None and item.episode is not None:
            season_data = self._season(show_id, item.season)
            if season_data:
                for ep in season_data.get("episodes", []):
                    if ep.get("episode_number") == item.episode:
                        info.episode_title = ep.get("name")
                        break
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
