from mediamaid.plugins import create, load_plugins


def _dl(mappings):
    load_plugins()
    return create("downloader", "qbittorrent", {"path_mappings": mappings})


def test_map_path_prefix_replace():
    dl = _dl(["/downloads:/data/downloads"])
    assert dl._map_path("/downloads/movie/x.mkv") == "/data/downloads/movie/x.mkv"
    assert dl._map_path("/downloads") == "/data/downloads"


def test_map_path_no_match_passthrough():
    dl = _dl(["/downloads:/data/downloads"])
    assert dl._map_path("/other/y.mkv") == "/other/y.mkv"


def test_map_path_longest_prefix_wins():
    dl = _dl(["/d:/x", "/d/movies:/library"])
    assert dl._map_path("/d/movies/a.mkv") == "/library/a.mkv"
    assert dl._map_path("/d/tv/b.mkv") == "/x/tv/b.mkv"


def test_map_path_empty_passthrough():
    dl = _dl([])
    assert dl._map_path("/downloads/x.mkv") == "/downloads/x.mkv"
