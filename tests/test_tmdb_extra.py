"""TMDB 优化：整季单请求取多集标题 + 缓存持久化 + 外部 ID。"""

from pathlib import Path

from mediamaid.models import MediaItem, MediaType
from mediamaid.plugins.scraper.tmdb import TMDBConfig, TMDBScraper, _TTLCache


def _episode(season=1, episode=1, title="Show", year=2008):
    return MediaItem(
        source=Path(f"{title}.S{season:02d}E{episode:02d}.mkv"),
        media_type=MediaType.EPISODE, title=title, year=year,
        season=season, episode=episode,
    )


def test_integral_season_single_request(monkeypatch):
    scraper = TMDBScraper(TMDBConfig(api_key="x"))
    season_calls = {"n": 0}

    def fake_get(path, **params):
        if path == "/search/tv":
            return {"results": [{"id": 1, "name": "Show", "original_name": "Show",
                                 "first_air_date": "2008-01-01", "overview": "",
                                 "poster_path": None, "backdrop_path": None}]}
        if path == "/tv/1":  # details
            return {"genres": [{"name": "Drama"}], "external_ids": {"imdb_id": "tt1", "tvdb_id": 7}}
        if path == "/tv/1/season/1":
            season_calls["n"] += 1
            return {"episodes": [
                {"episode_number": 1, "name": "Pilot"},
                {"episode_number": 2, "name": "Second"},
            ]}
        return None

    monkeypatch.setattr(scraper, "_get", fake_get)

    e1 = scraper.scrape(_episode(episode=1))
    e2 = scraper.scrape(_episode(episode=2))
    assert e1.episode_title == "Pilot"
    assert e2.episode_title == "Second"
    assert e1.imdb_id == "tt1" and e1.tvdb_id == 7 and "Drama" in e1.genres
    # 整季只请求一次（第二集命中缓存）
    assert season_calls["n"] == 1
    scraper.close()


def test_persistent_cache_survives_reload(tmp_path):
    path = tmp_path / "tmdb.json"
    c1 = _TTLCache(maxsize=10, ttl=3600, path=str(path))
    c1.set(("search", "movie", "X"), [{"id": 1}])
    assert path.exists()

    # 新建缓存从同一文件加载 → 命中
    c2 = _TTLCache(maxsize=10, ttl=3600, path=str(path))
    assert c2.get(("search", "movie", "X")) == [{"id": 1}]


def test_persistent_cache_expired_not_loaded(tmp_path):
    path = tmp_path / "tmdb.json"
    c1 = _TTLCache(maxsize=10, ttl=-1, path=str(path))  # 立即过期
    c1.set(("k",), "v")
    c2 = _TTLCache(maxsize=10, ttl=3600, path=str(path))
    assert c2.get(("k",)) is None
