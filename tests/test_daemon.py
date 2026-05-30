import threading
import time
from pathlib import Path

from mediamaid.config import Config
from mediamaid.daemon import Daemon
from mediamaid.models import Release
from mediamaid.pipeline import Pipeline
from mediamaid.plugins import Downloader, Subscriber, register
from mediamaid.store import StateStore

BIG = b"0" * (60 * 1024 * 1024)  # >50MB 过 min_size 过滤


def _cfg(tmp_path: Path, **extra) -> Config:
    src = tmp_path / "downloads"
    src.mkdir()
    extra.setdefault("plugins", {})
    return Config(
        source_dirs=[src],
        library_dir=tmp_path / "media",
        state_db=tmp_path / "s.db",
        **extra,
    )


# ---- process_target：文件 vs 目录 ----
def test_process_target_file(tmp_path):
    cfg = _cfg(tmp_path)
    f = cfg.source_dirs[0] / "The.Matrix.1999.1080p.mkv"
    f.write_bytes(BIG)
    with StateStore(cfg.state_db) as store:
        results = Pipeline(cfg, store).process_target(f)
    assert [r.status for r in results] == ["done"]


def test_process_target_directory(tmp_path):
    cfg = _cfg(tmp_path)
    d = cfg.source_dirs[0] / "Breaking.Bad.S01"
    d.mkdir()
    (d / "Breaking.Bad.S01E01.mkv").write_bytes(BIG)
    (d / "Breaking.Bad.S01E02.mkv").write_bytes(BIG)
    with StateStore(cfg.state_db) as store:
        results = Pipeline(cfg, store).process_target(d)
    assert sorted(r.status for r in results) == ["done", "done"]
    assert (cfg.library_dir / "TV" / "Breaking Bad" / "Season 01" /
            "Breaking Bad - S01E02.mkv").exists()


# ---- 完成轮询：整理 + 去重 ----
@register
class _CompletedDl(Downloader):
    name = "completed_dl_test"
    # 类属性，测试里设置返回哪些路径
    paths: list = []

    def add(self, release: Release) -> bool:
        return True

    def list_completed(self):
        return list(type(self).paths)


def test_poll_completed_organizes_then_dedups(tmp_path):
    cfg = _cfg(tmp_path, plugins={"downloader": [{"name": "completed_dl_test"}]})
    done_dir = tmp_path / "downloads" / "Inception.2010"
    done_dir.mkdir()
    (done_dir / "Inception.2010.1080p.mkv").write_bytes(BIG)
    _CompletedDl.paths = [done_dir]

    with StateStore(cfg.state_db) as store:
        daemon = Daemon(cfg, store)
        assert daemon._poll_completed_once() == 1
        assert (cfg.library_dir / "Movies" / "Inception (2010)" /
                "Inception (2010).mkv").exists()
        # 二次轮询：同样路径，因 is_done 去重，不再整理
        assert daemon._poll_completed_once() == 0


# ---- 线程级闭环：订阅→下载落盘→监控整理 ----
@register
class _LoopSub(Subscriber):
    name = "loop_sub_test"

    def fetch(self):
        return [Release(title="Inception 2010 1080p", guid="loop-1", magnet="magnet:?x")]


# 下载器把占位文件写进源目录，模拟下载完成
_DEST_DIR = {"path": None}


@register
class _LoopDl(Downloader):
    name = "loop_dl_test"

    def add(self, release: Release) -> bool:
        dst = _DEST_DIR["path"] / "Inception.2010.1080p.mkv"
        dst.write_bytes(BIG)
        return True


def test_closed_loop_end_to_end(tmp_path):
    cfg = _cfg(
        tmp_path,
        stable_seconds=1,
        rescan_interval=0,
        subscribe_interval=3600,  # 只跑启动那一轮
        plugins={
            "subscriber": [{"name": "loop_sub_test"}],
            "downloader": [{"name": "loop_dl_test"}],
        },
    )
    _DEST_DIR["path"] = cfg.source_dirs[0]

    with StateStore(cfg.state_db) as store:
        daemon = Daemon(cfg, store)
        t = threading.Thread(target=daemon.run, daemon=True)
        t.start()
        # 等待：订阅落盘 + 稳定(1s) + 整理
        dest = cfg.library_dir / "Movies" / "Inception (2010)" / "Inception (2010).mkv"
        deadline = time.time() + 15
        while time.time() < deadline and not dest.exists():
            time.sleep(0.3)
        daemon.stop()
        t.join(timeout=5)
        assert dest.exists(), "闭环未整理出目标文件"
