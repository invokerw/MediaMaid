from pathlib import Path

import pytest

from mediamaid.config import Config
from mediamaid.models import MediaInfo, MediaType, TransferAction
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


def test_anime_classified_by_genre(tmp_path):
    """借鉴 nas-tools：刮削题材含动画(genre 16) 的剧集归入 Anime/。"""
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "Shrouding.the.Heavens.S01E02.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        pipe.scrapers[0].scrape = lambda item: MediaInfo(
            title="Shrouding the Heavens", year=2023,
            season=item.season, episode=item.episode, genre_ids=[16], confidence=1.0,
        )
        pipe.scan()
    hits = list((cfg.library_dir / "Anime").rglob("*.mkv"))
    assert hits, "题材含动画(16)应整理进 Anime/ 目录"


def test_non_anime_episode_goes_to_tv(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "Breaking.Bad.S01E01.720p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        pipe.scrapers[0].scrape = lambda item: MediaInfo(
            title="Breaking Bad", year=2008,
            season=item.season, episode=item.episode, genre_ids=[18], confidence=1.0,
        )
        pipe.scan()
    assert list((cfg.library_dir / "TV").rglob("*.mkv"))
    assert not (cfg.library_dir / "Anime").exists()


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


def test_manual_override_info_and_force(tmp_path):
    """override_info 用其字段命名；force 跳过去重；unorganize 删目标+记录。"""
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    f = src / "Some.Movie.2020.1080p.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))

    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        item = pipe.identifier.identify(f)
        # 注入手填元数据：标题用 info 的（而非解析的 "Some Movie"）
        info = MediaInfo(title="正确片名", year=2021, tmdb_id=603, confidence=1.0)
        r1 = pipe.process_item(item, force=True, override_info=info)
        assert r1.status == "done"
        dest1 = cfg.library_dir / "Movies" / "正确片名 (2021)" / "正确片名 (2021).mkv"
        assert dest1.exists()
        assert store.is_done(f)

        # 不 force 第二次 → 跳过
        assert pipe.process_item(item, override_info=info).status == "skipped"

        # 撤销：删目标 + 记录
        assert pipe.unorganize(f) is True
        assert not dest1.exists()
        assert not store.is_done(f)

        # force 第二次（已撤销后）能重新落地
        assert pipe.process_item(item, force=True, override_info=info).status == "done"


def test_organize_manual_covering_correction(tmp_path):
    """organize_manual：改判到新位置后，旧目标被清理、记录指向新目标。"""
    cfg = _make_config(tmp_path)
    f = cfg.source_dirs[0] / "movie.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))

    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        item = pipe.identifier.identify(f)

        a = MediaInfo(title="片名A", year=2001, tmdb_id=1, confidence=1.0)
        item.media_type = MediaType.MOVIE
        r1 = pipe.organize_manual(item, a)
        old_dest = r1.dest
        assert old_dest.exists()

        # 改判到 B（不冲突）→ 旧目标删除、新目标存在、记录指向新目标
        b = MediaInfo(title="片名B", year=2002, tmdb_id=2, confidence=1.0)
        r2 = pipe.organize_manual(item, b)
        assert r2.status == "done"
        assert r2.dest.exists()
        assert not old_dest.exists()  # 旧目标已清理
        assert not old_dest.parent.exists()  # 空目录也清掉
        rec = store.done_record(f)
        assert rec.dst_path == str(r2.dest)


def test_organize_manual_conflict_restores_old(tmp_path):
    """新目标已被别的文件占用(skip) → 旧记录恢复、旧文件不丢。"""
    cfg = _make_config(tmp_path)  # on_conflict 默认 skip
    f = cfg.source_dirs[0] / "movie.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))

    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        item = pipe.identifier.identify(f)
        item.media_type = MediaType.MOVIE

        a = MediaInfo(title="片名A", year=2001, tmdb_id=1, confidence=1.0)
        r1 = pipe.organize_manual(item, a)
        old_dest = r1.dest

        # 预先占用 B 的目标路径（模拟另一个文件已在该位置）
        b = MediaInfo(title="片名B", year=2002, tmdb_id=2, confidence=1.0)
        b_dest = cfg.library_dir / "Movies" / "片名B (2002)" / "片名B (2002).mkv"
        b_dest.parent.mkdir(parents=True, exist_ok=True)
        b_dest.write_bytes(b"occupied")

        r2 = pipe.organize_manual(item, b)
        assert r2.status == "skipped"
        # 旧目标与旧记录都还在（未被破坏）
        assert old_dest.exists()
        assert store.done_record(f).dst_path == str(old_dest)
        # 占用文件未被覆盖
        assert b_dest.read_bytes() == b"occupied"


def test_tmdb_rule_ignore_skips(tmp_path):
    """命中绑定规则得到 tmdb_id，且该季集被 ignore → 整理时跳过不落地。"""
    from mediamaid.config import IgnoreEpisodes, TmdbRule

    cfg = _make_config(tmp_path)
    cfg.tmdb_rules = [
        TmdbRule(
            id="r1", tmdb_id=42, media_type="episode",
            patterns=[r"FANSUB.*?(?P<episode>\d+)"], season=1,
            ignore_episodes=[IgnoreEpisodes(season=1, episodes=[13])],
        )
    ]
    src = cfg.source_dirs[0]
    (src / "FANSUB - 13.mkv").write_bytes(b"0" * (60 * 1024 * 1024))  # 被忽略
    (src / "FANSUB - 14.mkv").write_bytes(b"0" * (60 * 1024 * 1024))  # 不忽略

    with StateStore(cfg.state_db) as store:
        results = {r.item.source.name: r.status for r in Pipeline(cfg, store).scan()}
    assert results["FANSUB - 13.mkv"] == "skipped"
    assert results["FANSUB - 14.mkv"] == "done"


def _boom(*a, **k):
    raise OSError("disk full")


def test_failed_file_moved_to_failed_dir(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    cfg.failed_dir = cfg.source_dirs[0] / "_failed"  # 故意放在源目录内，验证排除
    f = cfg.source_dirs[0] / "Boom.2020.1080p.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))

    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        monkeypatch.setattr(pipe.organizer, "execute", _boom)  # 强制落地失败
        results = pipe.scan()
        assert [r.status for r in results] == ["failed"]
        # 源文件已移入失败目录
        assert not f.exists()
        assert (cfg.failed_dir / "Boom.2020.1080p.mkv").exists()
        # 记录 dst 指向失败落点
        rec = store.recent()[0]
        assert rec.status == "failed" and rec.dst_path and "_failed" in rec.dst_path

    # 再次扫描：失败目录被排除，不再处理
    with StateStore(cfg.state_db) as store:
        assert Pipeline(cfg, store).scan() == []


def test_failed_file_stays_without_failed_dir(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)  # failed_dir 未配置
    f = cfg.source_dirs[0] / "Boom.2020.1080p.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        monkeypatch.setattr(pipe.organizer, "execute", _boom)
        results = pipe.scan()
    assert [r.status for r in results] == ["failed"]
    assert f.exists()  # 留在原地


def test_unidentified_moved_to_failed_dir(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    cfg.failed_dir = tmp_path / "failed"
    f = cfg.source_dirs[0] / "garbled.release.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        monkeypatch.setattr(pipe.identifier, "identify", lambda p: None)  # 模拟识别失败
        results = pipe.scan()
        assert [r.status for r in results] == ["failed"]
        assert not f.exists()
        assert (cfg.failed_dir / "garbled.release.mkv").exists()
        rec = store.recent()[0]
        assert rec.status == "failed" and rec.dst_path and "failed" in rec.dst_path


def test_unidentified_stays_without_failed_dir(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)  # 未配 failed_dir
    f = cfg.source_dirs[0] / "garbled.release.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        monkeypatch.setattr(pipe.identifier, "identify", lambda p: None)
        assert pipe.scan() == []  # 不记录、不处理
    assert f.exists()  # 留在原地


def test_unknown_type_moved_to_failed_dir(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    cfg.failed_dir = tmp_path / "failed"
    f = cfg.source_dirs[0] / "mystery.mkv"
    f.write_bytes(b"0" * (60 * 1024 * 1024))
    from mediamaid.models import MediaItem, MediaType as MT
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        monkeypatch.setattr(
            pipe.identifier, "identify",
            lambda p: MediaItem(source=p, media_type=MT.UNKNOWN, title="x"),
        )
        results = pipe.scan()
        assert [r.status for r in results] == ["failed"]
        assert (cfg.failed_dir / "mystery.mkv").exists()


def test_under_failed(tmp_path):
    cfg = _make_config(tmp_path)
    assert cfg.under_failed(tmp_path / "a.mkv") is False  # 未配置
    cfg.failed_dir = tmp_path / "failed"
    assert cfg.under_failed(tmp_path / "failed" / "a.mkv") is True
    assert cfg.under_failed(tmp_path / "failed") is True
    assert cfg.under_failed(tmp_path / "other" / "a.mkv") is False


def test_dedup_skips_second_run(tmp_path):
    cfg = _make_config(tmp_path)
    src = cfg.source_dirs[0]
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(b"0" * (60 * 1024 * 1024))
    with StateStore(cfg.state_db) as store:
        pipe = Pipeline(cfg, store)
        pipe.scan()
        results = pipe.scan()
    assert all(r.status == "skipped" for r in results)
