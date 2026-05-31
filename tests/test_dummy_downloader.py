from mediamaid.models import Release
from mediamaid.plugins import create, load_plugins


def test_dummy_creates_placeholder(tmp_path):
    load_plugins()
    dl = create("downloader", "dummy", {"save_path": str(tmp_path), "size_mb": 60})

    ok = dl.add(Release(title="The.Matrix.1999.1080p", guid="g1", magnet="magnet:?x"))
    assert ok is True

    f = tmp_path / "The.Matrix.1999.1080p.mkv"
    assert f.exists()
    assert f.stat().st_size == 60 * 1024 * 1024  # 稀疏，st_size 达标
    assert dl.list_completed() == [f]


def test_dummy_keeps_existing_extension(tmp_path):
    load_plugins()
    dl = create("downloader", "dummy", {"save_path": str(tmp_path), "size_mb": 1})
    dl.add(Release(title="Show.S01E01.mp4", guid="g2"))
    assert (tmp_path / "Show.S01E01.mp4").exists()
