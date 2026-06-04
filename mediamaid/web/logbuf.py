"""进程内日志环形缓冲：供 Web「日志」页展示通知器/流水线日志。"""

from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Dict, List


class RingBufferHandler(logging.Handler):
    """把日志记录存进定长 deque（最新在末尾），供 /api/logs 读取。"""

    def __init__(self, maxlen: int = 500):
        super().__init__()
        self.records: Deque[Dict] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(
                {
                    "ts": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
            )
        except Exception:  # noqa: BLE001 - 日志缓冲不可影响主流程
            pass

    def tail(self, limit: int = 200) -> List[Dict]:
        """返回最近 limit 条（新→旧）。"""
        items = list(self.records)[-limit:]
        items.reverse()
        return items


# 模块单例：app 启动时挂到 logger "mediamaid"
LOG_BUFFER = RingBufferHandler()
