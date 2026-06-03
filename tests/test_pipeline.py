from pathlib import Path

import pytest

from mediamaid.config import Config
from mediamaid.models import TransferAction
from mediamaid.pipeline import Pipeline, build_scrapers
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
        plugins={},  # 不启用任何刮削器 -> null 兜底
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


def test_anime_keyword_routes_to_anime_dir(tmp_path):
    cfg = _make_config(tmp_path)
    cfg.anime_keywords = ["anime"]
    src = cfg.source_dirs[0]
    anime_dir = src / "anime"
    anime_dir.mkdir()
    (anime_dir / "Shrouding.the.Heavens.S01E02.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        Pipeline(cfg, store).scan()
    # 命中 anime 关键词 → 进 Anime/ 目录
    hits = list((cfg.library_dir / "Anime").rglob("*.mkv"))
    assert hits, "动漫文件应整理进 Anime/ 目录"


def test_build_scrapers_requires_tmdb_key(tmp_path):
    # 顶层 import 的 build_scrapers 指向原函数，不受 conftest 桩替换影响。
    base = _make_config(tmp_path)  # 借其路径，构造不同 plugins 的 Config

    def _cfg(plugins):
        return Config(
            source_dirs=base.source_dirs,
            library_dir=base.library_dir,
            state_db=base.state_db,
            plugins=plugins,
        )

    # 无 tmdb 配置 / 空 api_key 都应报错
    with pytest.raises(RuntimeError, match="TMDB"):
        build_scrapers(_cfg({}))
    with pytest.raises(RuntimeError, match="TMDB"):
        build_scrapers(_cfg({"scraper": [{"name": "tmdb", "config": {"api_key": ""}}]}))
    # 配了 api_key 则固定返回 tmdb
    scrapers = build_scrapers(_cfg({"scraper": [{"name": "tmdb", "config": {"api_key": "k"}}]}))
    assert [s.name for s in scrapers] == ["tmdb"]


def test_dedup_skips_second_run(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        pipe.scan()
        results = pipe.scan()
    assert all(r.status == "skipped" for r in results)
