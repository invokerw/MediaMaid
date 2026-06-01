"""状态库（SQLite）：去重、记录映射、支持 undo。

并发模型：每个线程持有自己的连接（thread-local），开启 WAL + busy_timeout，
让读不互相阻塞、写由 SQLite 自身串行化，无需进程内全局锁。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
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
    batch_id    TEXT,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_src ON processed(src_path);
CREATE INDEX IF NOT EXISTS idx_processed_inode ON processed(src_inode);
CREATE INDEX IF NOT EXISTS idx_processed_batch ON processed(batch_id);

CREATE TABLE IF NOT EXISTS seen_releases (
    guid   TEXT PRIMARY KEY,
    title  TEXT,
    sub_id TEXT,
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
        self._local = threading.local()
        # 记录所有已建连接，便于 close() 全部关闭
        self._conns: List[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        # 用一条初始化连接建表/迁移
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)
            conn.commit()

    # ---- 连接管理（thread-local）----
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # WAL：读不阻塞写；busy_timeout：并发写时等待而非立刻报错
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        with self._conns_lock:
            self._conns.append(conn)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """当前线程的连接（首次访问时创建）。"""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._connect()
            self._local.conn = c
        return c

    def close(self) -> None:
        with self._conns_lock:
            for c in self._conns:
                try:
                    c.close()
                except sqlite3.Error:
                    pass
            self._conns.clear()
        self._local = threading.local()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """旧库补列（幂等）。"""
        rcols = {r["name"] for r in conn.execute("PRAGMA table_info(seen_releases)")}
        if "sub_id" not in rcols:
            conn.execute("ALTER TABLE seen_releases ADD COLUMN sub_id TEXT")
        pcols = {r["name"] for r in conn.execute("PRAGMA table_info(processed)")}
        if "batch_id" not in pcols:
            conn.execute("ALTER TABLE processed ADD COLUMN batch_id TEXT")

    @staticmethod
    def _inode(path: Path) -> Optional[int]:
        try:
            return path.stat().st_ino
        except OSError:
            return None

    @staticmethod
    def new_batch_id() -> str:
        """生成一个批次标识，供一次扫描/整理动作内的所有记录共享。"""
        return uuid.uuid4().hex[:12]

    def is_done(self, src: Path) -> bool:
        """该源文件是否已成功处理（按路径+inode 去重）。"""
        inode = self._inode(src)
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
        batch_id: Optional[str] = None,
    ) -> bool:
        """写一条处理记录。

        status='done' 时用条件插入做 DB 层兜底去重：若已存在该源文件的 done 记录
        则不再插入（防止 watcher 与完成轮询并发重复整理同一文件产生重复记录）。
        返回是否真正插入。
        """
        try:
            size = src.stat().st_size
        except OSError:
            size = None
        inode = self._inode(src)
        row = (
            str(src), inode, size, str(dst) if dst else None,
            action, status, error, batch_id, time.time(),
        )
        conn = self.conn
        if status == "done":
            cur = conn.execute(
                "INSERT INTO processed "
                "(src_path, src_inode, src_size, dst_path, action, status, error, batch_id, ts) "
                "SELECT ?,?,?,?,?,?,?,?,? WHERE NOT EXISTS ("
                "  SELECT 1 FROM processed WHERE status='done' AND "
                "  (src_path=? OR (src_inode IS NOT NULL AND src_inode=?)))",
                (*row, str(src), inode),
            )
            conn.commit()
            return cur.rowcount > 0
        conn.execute(
            "INSERT INTO processed "
            "(src_path, src_inode, src_size, dst_path, action, status, error, batch_id, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            row,
        )
        conn.commit()
        return True

    def recent(self, limit: int = 50) -> List[Record]:
        cur = self.conn.execute(
            "SELECT id, src_path, dst_path, action, status, ts "
            "FROM processed ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [self._to_record(r) for r in cur.fetchall()]

    def counts(self) -> dict:
        """按状态聚合处理记录数量。"""
        cur = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM processed GROUP BY status"
        )
        return {r["status"]: r["n"] for r in cur.fetchall()}

    def last_batch_done(self) -> List[Record]:
        """返回最近一批成功(done)的记录，供 undo。

        优先按 batch_id 精确圈定（新记录都带 batch_id）；最新 done 记录无 batch_id
        的旧库则回退到"最近 5 分钟内"的时间窗近似。
        """
        cur = self.conn.execute(
            "SELECT id, src_path, dst_path, action, status, batch_id, ts "
            "FROM processed WHERE status='done' ORDER BY id DESC"
        )
        rows = cur.fetchall()
        if not rows:
            return []
        newest = rows[0]
        if newest["batch_id"]:
            batch = [r for r in rows if r["batch_id"] == newest["batch_id"]]
        else:
            cutoff = newest["ts"] - 300  # 旧库回退：5 分钟时间窗
            batch = [r for r in rows if r["ts"] >= cutoff]
        return [self._to_record(r) for r in batch]

    def delete(self, record_id: int) -> None:
        self.conn.execute("DELETE FROM processed WHERE id=?", (record_id,))
        self.conn.commit()

    @staticmethod
    def _to_record(r: sqlite3.Row) -> Record:
        return Record(r["id"], r["src_path"], r["dst_path"], r["action"], r["status"], r["ts"])

    # ---- 订阅去重 ----
    def release_seen(self, guid: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM seen_releases WHERE guid=? LIMIT 1", (guid,)
        )
        return cur.fetchone() is not None

    def mark_release(self, guid: str, title: str = "", sub_id: Optional[str] = None) -> None:
        conn = self.conn
        conn.execute(
            "INSERT OR IGNORE INTO seen_releases (guid, title, sub_id, ts) "
            "VALUES (?,?,?,?)",
            (guid, title, sub_id, time.time()),
        )
        conn.commit()

    def recent_releases(self, limit: int = 200) -> List[tuple]:
        """返回已处理(见过)的资源 [(guid, title, ts), ...]，最近在前。"""
        cur = self.conn.execute(
            "SELECT guid, title, ts FROM seen_releases ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        return [(r["guid"], r["title"], r["ts"]) for r in cur.fetchall()]

    def releases_for(self, sub_id: str, limit: int = 200) -> List[tuple]:
        """某订阅已处理的资源 [(guid, title, ts), ...]，最近在前。"""
        cur = self.conn.execute(
            "SELECT guid, title, ts FROM seen_releases WHERE sub_id=? "
            "ORDER BY ts DESC LIMIT ?",
            (sub_id, limit),
        )
        return [(r["guid"], r["title"], r["ts"]) for r in cur.fetchall()]

    def count_for(self, sub_id: str) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) AS n FROM seen_releases WHERE sub_id=?", (sub_id,)
        )
        return cur.fetchone()["n"]
