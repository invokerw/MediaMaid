"""状态库（SQLite）：去重、记录映射、支持 undo。"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import List, NamedTuple, Optional

from .logging_conf import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_path    TEXT NOT NULL,
    src_inode   INTEGER,
    src_size    INTEGER,
    dst_path    TEXT,
    action      TEXT,
    status      TEXT NOT NULL,
    error       TEXT,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_src ON processed(src_path);
CREATE INDEX IF NOT EXISTS idx_processed_inode ON processed(src_inode);

CREATE TABLE IF NOT EXISTS seen_releases (
    guid   TEXT PRIMARY KEY,
    title  TEXT,
    ts     REAL NOT NULL
);
"""


class Record(NamedTuple):
    id: int
    src_path: str
    dst_path: Optional[str]
    action: Optional[str]
    status: str
    ts: float


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # watcher 在后台线程写库，需允许跨线程并用锁串行化访问
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            # WAL：读不阻塞写，便于 Web 与守护进程并发访问同一库
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def _inode(path: Path) -> Optional[int]:
        try:
            return path.stat().st_ino
        except OSError:
            return None

    def is_done(self, src: Path) -> bool:
        """该源文件是否已成功处理（按路径+inode 去重）。"""
        inode = self._inode(src)
        with self._lock:
            cur = self.conn.execute(
                "SELECT 1 FROM processed WHERE status='done' AND "
                "(src_path=? OR (src_inode IS NOT NULL AND src_inode=?)) LIMIT 1",
                (str(src), inode),
            )
            return cur.fetchone() is not None

    def record(
        self,
        src: Path,
        dst: Optional[Path],
        action: Optional[str],
        status: str,
        error: Optional[str] = None,
    ) -> None:
        try:
            size = src.stat().st_size
        except OSError:
            size = None
        with self._lock:
            self.conn.execute(
                "INSERT INTO processed "
                "(src_path, src_inode, src_size, dst_path, action, status, error, ts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(src),
                    self._inode(src),
                    size,
                    str(dst) if dst else None,
                    action,
                    status,
                    error,
                    time.time(),
                ),
            )
            self.conn.commit()

    def recent(self, limit: int = 50) -> List[Record]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, src_path, dst_path, action, status, ts "
                "FROM processed ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [
            Record(r["id"], r["src_path"], r["dst_path"], r["action"], r["status"], r["ts"])
            for r in rows
        ]

    def counts(self) -> dict:
        """按状态聚合处理记录数量。"""
        with self._lock:
            cur = self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM processed GROUP BY status"
            )
            return {r["status"]: r["n"] for r in cur.fetchall()}

    def last_batch_done(self) -> List[Record]:
        """返回最近一批（同一最大时间戳秒附近）成功的记录，供 undo。

        简单实现：取最近一次 run 内 status='done' 的记录。这里以"最近 N 条
        连续 done"近似一个批次，调用方可据 ts 进一步筛选。
        """
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, src_path, dst_path, action, status, ts "
                "FROM processed WHERE status='done' ORDER BY id DESC"
            )
            rows = cur.fetchall()
        if not rows:
            return []
        # 以最近记录时间为基准，5 分钟内视为同一批
        newest = rows[0]["ts"]
        batch = [r for r in rows if newest - r["ts"] <= 300]
        return [
            Record(r["id"], r["src_path"], r["dst_path"], r["action"], r["status"], r["ts"])
            for r in batch
        ]

    def delete(self, record_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM processed WHERE id=?", (record_id,))
            self.conn.commit()

    # ---- 订阅去重 ----
    def release_seen(self, guid: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "SELECT 1 FROM seen_releases WHERE guid=? LIMIT 1", (guid,)
            )
            return cur.fetchone() is not None

    def mark_release(self, guid: str, title: str = "") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO seen_releases (guid, title, ts) VALUES (?,?,?)",
                (guid, title, time.time()),
            )
            self.conn.commit()

    def recent_releases(self, limit: int = 200) -> List[tuple]:
        """返回已处理(见过)的资源 [(guid, title, ts), ...]，最近在前。"""
        with self._lock:
            cur = self.conn.execute(
                "SELECT guid, title, ts FROM seen_releases ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            return [(r["guid"], r["title"], r["ts"]) for r in cur.fetchall()]
