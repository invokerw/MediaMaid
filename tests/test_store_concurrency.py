"""状态库的并发与批次相关行为：thread-local 连接、done 去重、batch_id。"""

import threading
from pathlib import Path

from mediamaid.store import StateStore


def test_done_record_deduped(tmp_path):
    """同一源文件重复 record('done') 只落一条（DB 层兜底去重）。"""
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x" * 100)
    dst = tmp_path / "lib" / "a.mkv"
    with StateStore(tmp_path / "s.db") as store:
        assert store.record(src, dst, "hardlink", "done") is True
        # 第二次相同源文件的 done 不应再插入
        assert store.record(src, dst, "hardlink", "done") is False
        done = [r for r in store.recent() if r.status == "done"]
        assert len(done) == 1


def test_batch_id_groups_undo(tmp_path):
    """last_batch_done 按 batch_id 精确圈定最近一批。"""
    with StateStore(tmp_path / "s.db") as store:
        b1 = store.new_batch_id()
        store.record(tmp_path / "a.mkv", tmp_path / "lib/a.mkv", "copy", "done", batch_id=b1)
        store.record(tmp_path / "b.mkv", tmp_path / "lib/b.mkv", "copy", "done", batch_id=b1)
        b2 = store.new_batch_id()
        store.record(tmp_path / "c.mkv", tmp_path / "lib/c.mkv", "copy", "done", batch_id=b2)

        batch = store.last_batch_done()
        assert len(batch) == 1  # 最近一批只有 c
        assert Path(batch[0].dst_path).name == "c.mkv"


def test_threadlocal_connections_allow_concurrent_writes(tmp_path):
    """多线程并发写不报 '另一个线程的连接' 错，记录数正确。"""
    with StateStore(tmp_path / "s.db") as store:
        def worker(i: int):
            store.record(
                tmp_path / f"f{i}.mkv", tmp_path / f"lib/f{i}.mkv", "copy", "done"
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        done = [r for r in store.recent(100) if r.status == "done"]
        assert len(done) == 20
