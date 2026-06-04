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


def test_done_record_and_done_for(tmp_path):
    a = tmp_path / "a.mkv"
    b = tmp_path / "b.mkv"
    c = tmp_path / "c.mkv"
    for p in (a, b, c):
        p.write_bytes(b"x" * 100)
    with StateStore(tmp_path / "s.db") as store:
        store.record(a, tmp_path / "lib" / "A.mkv", "hardlink", "done")
        store.record(b, None, "copy", "failed", "boom")  # 非 done 不计入
        # done_record：命中返回含目标与动作，未命中 None
        rec = store.done_record(a)
        assert rec is not None and rec.dst_path.endswith("A.mkv") and rec.action == "hardlink"
        assert store.done_record(b) is None
        assert store.done_record(c) is None
        # done_for：批量只返回 done 的
        m = store.done_for([a, b, c])
        assert set(m) == {str(a)}
        assert m[str(a)].dst_path.endswith("A.mkv")
        assert store.done_for([]) == {}


def test_delete_many_and_set_status(tmp_path):
    with StateStore(tmp_path / "s.db") as store:
        for i in range(3):
            store.record(tmp_path / f"{i}.mkv", tmp_path / f"lib/{i}.mkv", "copy", "failed")
        ids = [r.id for r in store.recent()]
        assert len(ids) == 3
        # 改状态
        assert store.set_status(ids[:2], "done") == 2
        statuses = {r.id: r.status for r in store.recent()}
        assert statuses[ids[0]] == "done" and statuses[ids[2]] == "failed"
        # 批量删除
        assert store.delete_many(ids[:2]) == 2
        assert len(store.recent()) == 1
        # 空入参安全
        assert store.delete_many([]) == 0 and store.set_status([], "done") == 0


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
