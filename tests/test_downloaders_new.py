"""transmission / aria2 下载器：注册、配置校验、PathMapper、空链接处理。"""

from mediamaid.models import Release
from mediamaid.plugins import available, create, load_plugins
from mediamaid.plugins.downloader import PathMapper


def test_path_mapper_longest_prefix():
    m = PathMapper(["/d:/x", "/d/movies:/library"])
    assert m.map("/d/movies/a.mkv") == "/library/a.mkv"
    assert m.map("/d/tv/b.mkv") == "/x/tv/b.mkv"
    assert m.map("/other/c.mkv") == "/other/c.mkv"


def test_new_downloaders_registered():
    load_plugins()
    names = available("downloader")
    assert "transmission" in names
    assert "aria2" in names


def test_transmission_config_and_mapper():
    dl = create("downloader", "transmission", {"path_mappings": ["/dl:/data"]})
    assert dl._mapper.map("/dl/x.mkv") == "/data/x.mkv"
    # 无链接 → 不提交
    assert dl.add(Release(title="x", guid="g")) is False


def test_aria2_config_and_empty_uri():
    dl = create("downloader", "aria2", {"secret": "s", "path_mappings": ["/dl:/data"]})
    assert dl._mapper.map("/dl/x.mkv") == "/data/x.mkv"
    assert dl.add(Release(title="x", guid="g")) is False
    dl.close()
