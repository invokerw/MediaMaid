"""NFO 生成：电影/剧集外部 ID + tvshow.nfo。"""

import xml.etree.ElementTree as ET

from mediamaid import nfo
from mediamaid.models import MediaInfo, MediaType


def test_movie_nfo_has_external_ids_and_genres(tmp_path):
    f = tmp_path / "Movie (2020).mkv"
    f.write_bytes(b"x")
    info = MediaInfo(
        title="Movie", year=2020, tmdb_id=11, imdb_id="tt123",
        genres=["科幻", "动作"], rating=8.5,
    )
    dest = nfo.write_nfo(f, info, MediaType.MOVIE)
    root = ET.parse(dest).getroot()
    assert root.tag == "movie"
    ids = {(u.get("type"), u.text) for u in root.findall("uniqueid")}
    assert ("tmdb", "11") in ids
    assert ("imdb", "tt123") in ids
    assert {g.text for g in root.findall("genre")} == {"科幻", "动作"}
    assert root.findtext("rating") == "8.5"


def test_episode_writes_tvshow_nfo_at_series_root(tmp_path):
    # 剧集根/Season 01/文件.mkv
    ep = tmp_path / "Show (2008)" / "Season 01" / "Show - S01E01.mkv"
    ep.parent.mkdir(parents=True)
    ep.write_bytes(b"x")
    info = MediaInfo(
        title="Show", year=2008, tmdb_id=22, imdb_id="tt999", tvdb_id=555,
        season=1, episode=1, episode_title="Pilot", genres=["剧情"],
    )
    nfo.write_nfo(ep, info, MediaType.EPISODE)
    series_root = ep.parent.parent
    nfo.write_tvshow_nfo(series_root, info)

    tvshow = series_root / "tvshow.nfo"
    assert tvshow.exists()
    root = ET.parse(tvshow).getroot()
    assert root.tag == "tvshow"
    assert root.findtext("title") == "Show"
    ids = {(u.get("type"), u.text) for u in root.findall("uniqueid")}
    assert ("tmdb", "22") in ids and ("imdb", "tt999") in ids and ("tvdb", "555") in ids


def test_tvshow_nfo_not_overwritten(tmp_path):
    root = tmp_path / "Show"
    root.mkdir()
    existing = root / "tvshow.nfo"
    existing.write_text("<tvshow><title>手工编辑</title></tvshow>", encoding="utf-8")
    nfo.write_tvshow_nfo(root, MediaInfo(title="Show", year=2008))
    assert "手工编辑" in existing.read_text(encoding="utf-8")  # 未被覆盖
