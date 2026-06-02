"""测试下载器：收到任务后在指定目录创建占位文件，模拟下载完成。

用于在没有真实下载客户端（qBittorrent 等）时联调整条闭环：
订阅→(本下载器建文件)→监控识别→刮削→整理。
占位文件用稀疏文件，几乎不占磁盘但 st_size 达到设定大小以通过体积过滤。
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Release
from ..base import Downloader
from ..registry import register

log = get_logger(__name__)

_VIDEO_EXTS = {"mkv", "mp4", "avi", "ts", "m2ts", "mov", "wmv", "flv", "iso"}


class DummyConfig(BaseModel):
    # 占位文件落地目录（建议设为某个 source_dirs，便于被监控整理）
    save_path: str
    # 占位文件大小(MB)，需 >= 过滤器 min_size_mb 才会被识别
    size_mb: int = 60
    # 无扩展名时补的视频扩展名
    extension: str = "mkv"


@register
class DummyDownloader(Downloader):
    name = "dummy"
    description = "测试下载器，在指定目录创建占位文件以联调整条闭环"
    ConfigModel = DummyConfig

    def __init__(self, config: DummyConfig):
        super().__init__(config)
        self._created: List[Path] = []

    def _filename(self, release: Release) -> str:
        name = release.title.strip() or "Unknown"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _VIDEO_EXTS:
            name = f"{name}.{self.config.extension}"
        return name

    def add(self, release: Release) -> bool:
        cfg: DummyConfig = self.config
        dest = Path(cfg.save_path) / self._filename(release)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = max(1, cfg.size_mb) * 1024 * 1024
            # 稀疏文件：seek 到末尾写 1 字节，st_size 达标但几乎不占磁盘
            with open(dest, "wb") as f:
                f.seek(size - 1)
                f.write(b"\0")
            self._created.append(dest)
            log.info("测试下载器已创建占位文件: %s (%dMB)", dest, cfg.size_mb)
            return True
        except OSError as e:
            log.error("测试下载器创建文件失败 %s: %s", dest, e)
            return False

    def list_completed(self) -> List[Path]:
        return [p for p in self._created if p.exists()]
