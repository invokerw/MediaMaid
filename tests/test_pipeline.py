from pathlib import Path

from mediamaid.config import Config
from mediamaid.models import TransferAction
from mediamaid.pipeline import Pipeline
from mediamaid.store import StateStore


def _make_config(tmp_path: Path, action=TransferAction.HARDLINK) -> Config:
    src = tmp_path / "downloads"
    src.mkdir()
    lib = tmp_path / "media"
    return Config(
        source_dirs=[src],
        library_dir=lib,
        action=action,
        state_db=tmp_path / "s.db",
        scraper={"enabled": False},
    )


def test_scan_organizes_files(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    # 造两个 >50MB 的占位文件
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    (src / "Breaking.Bad.S01E01.720p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))

    with StateStore(cfg.state_db) as store:
        results = Pipeline(cfg, store).scan()

    statuses = sorted(r.status for r in results)
    assert statuses == ["done", "done"]
    assert (cfg.library_dir / "Movies" / "The Matrix (1999)" / "The Matrix (1999).mkv").exists()
    assert (
        cfg.library_dir / "TV" / "Breaking Bad" / "Season 01" / "Breaking Bad - S01E01.mkv"
    ).exists()


def test_dry_run_does_not_write(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        Pipeline(cfg, store).scan(dry_run=True)
    assert not cfg.library_dir.exists()


def test_dedup_skips_second_run(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        pipe.scan()
        results = pipe.scan()
    assert all(r.status == "skipped" for r in results)
