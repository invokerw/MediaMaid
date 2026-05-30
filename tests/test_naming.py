from pathlib import Path

from mediamaid import naming
from mediamaid.config import NamingConfig
from mediamaid.models import MediaInfo, MediaItem, MediaType


def test_movie_path():
    item = MediaItem(Path("x.mkv"), MediaType.MOVIE, "The Matrix", year=1999)
    dest = naming.render_dest(item, None, NamingConfig())
    assert dest == Path("Movies/The Matrix (1999)/The Matrix (1999).mkv")


def test_movie_no_year():
    item = MediaItem(Path("x.mp4"), MediaType.MOVIE, "Untitled")
    dest = naming.render_dest(item, None, NamingConfig())
    assert dest == Path("Movies/Untitled/Untitled.mp4")


def test_episode_path():
    item = MediaItem(Path("x.mkv"), MediaType.EPISODE, "Breaking Bad", year=2008, season=3, episode=7)
    dest = naming.render_dest(item, None, NamingConfig())
    assert dest == Path("TV/Breaking Bad (2008)/Season 03/Breaking Bad - S03E07.mkv")


def test_scraped_info_overrides_title():
    item = MediaItem(Path("x.mkv"), MediaType.MOVIE, "the matrix", year=1999)
    info = MediaInfo(title="The Matrix", year=1999, tmdb_id=603, confidence=0.9)
    dest = naming.render_dest(item, info, NamingConfig())
    assert dest == Path("Movies/The Matrix (1999)/The Matrix (1999).mkv")


def test_sanitize_illegal_chars():
    assert naming.sanitize('a/b:c*?d') == "a b c d"
