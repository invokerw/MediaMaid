"""TMDB 刮削器缓存：瞬时失败不投毒 + LRU/TTL 行为。"""

from mediamaid.models import MediaItem, MediaType
from mediamaid.plugins.scraper.tmdb import TMDBConfig, TMDBScraper, _TTLCache


def _movie(title="The Matrix", year=1999):
    return MediaItem(source=__import__("pathlib").Path(f"{title}.mkv"),
                     media_type=MediaType.MOVIE, title=title, year=year)


def test_ttlcache_lru_eviction():
    c = _TTLCache(maxsize=2, ttl=1000)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")          # 触达 a，使 b 成为最久未用
    c.set("c", 3)       # 触发淘汰 -> 应淘汰 b
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_ttlcache_expiry(monkeypatch):
    import mediamaid.plugins.scraper.tmdb as mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: now["t"])
    c = _TTLCache(maxsize=10, ttl=5)
    c.set("k", 42)
    assert c.get("k") == 42
    now["t"] += 6  # 超过 ttl
    assert c.get("k") is None


def test_transient_failure_not_cached(monkeypatch):
    """_get 返回 None（瞬时失败）时不缓存；恢复后下次能拿到结果。"""
    scraper = TMDBScraper(TMDBConfig(api_key="x"))
    calls = {"n": 0}

    def fake_get(path, **params):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # 首次模拟网络失败
        return {"results": [
            {"id": 603, "title": "The Matrix", "original_title": "The Matrix",
             "release_date": "1999-03-31", "overview": "", "poster_path": None,
             "backdrop_path": None}
        ]}

    monkeypatch.setattr(scraper, "_get", fake_get)

    item = _movie()
    assert scraper.scrape(item) is None          # 失败：返回 None
    info = scraper.scrape(item)                   # 重试：这次成功（说明上次没被缓存毒化）
    assert info is not None and info.tmdb_id == 603
    # 失败重试(1) + 成功搜索(2) + 拉详情补 genres/imdb(3)
    assert calls["n"] == 3
    scraper.close()


def test_successful_empty_result_is_cached(monkeypatch):
    """成功但无结果会被缓存，不再重复请求。"""
    scraper = TMDBScraper(TMDBConfig(api_key="x"))
    calls = {"n": 0}

    def fake_get(path, **params):
        calls["n"] += 1
        return {"results": []}

    monkeypatch.setattr(scraper, "_get", fake_get)
    item = _movie()
    assert scraper.scrape(item) is None
    assert scraper.scrape(item) is None
    assert calls["n"] == 1  # 第二次命中缓存，没有再请求
    scraper.close()
