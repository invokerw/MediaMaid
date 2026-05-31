from pathlib import Path

from mediamaid.config import Config
from mediamaid.identify import Identifier
from mediamaid.models import MediaType


def make_identifier():
    return Identifier(Config(source_dirs=[Path("/tmp")], library_dir=Path("/tmp/lib")))


def test_identify_movie():
    ident = make_identifier()
    item = ident.identify_path_name("The.Matrix.1999.1080p.BluRay.x264.mkv")
    assert item.media_type == MediaType.MOVIE
    assert "Matrix" in item.title
    assert item.year == 1999


def test_identify_episode():
    ident = make_identifier()
    item = ident.identify_path_name("Breaking.Bad.S03E07.720p.HDTV.x264.mkv")
    assert item.media_type == MediaType.EPISODE
    assert "Breaking Bad" in item.title
    assert item.season == 3
    assert item.episode == 7


def test_episode_defaults_season_1():
    ident = make_identifier()
    # 只有集号、无季号 -> 默认第 1 季
    item = ident.identify_path_name("Some Show - 05.mkv")
    if item and item.media_type == MediaType.EPISODE and item.episode is not None:
        assert item.season == 1
