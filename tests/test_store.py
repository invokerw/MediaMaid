from pathlib import Path

from mediamaid.store import StateStore


def test_dedup_and_record(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x" * 100)
    dst = tmp_path / "lib" / "a.mkv"
    with StateStore(tmp_path / "s.db") as store:
        assert not store.is_done(src)
        store.record(src, dst, "hardlink", "done")
        assert store.is_done(src)


def test_recent_and_batch(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x" * 100)
    with StateStore(tmp_path / "s.db") as store:
        store.record(src, tmp_path / "lib" / "a.mkv", "copy", "done")
        store.record(src, None, "copy", "failed", "boom")
        recent = store.recent()
        assert len(recent) == 2
        batch = store.last_batch_done()
        assert len(batch) == 1
        assert batch[0].status == "done"
