"""识别：遍历源目录，用 guessit 解析文件名为 MediaItem。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

from guessit import guessit

from .config import FilterConfig
from .logging_conf import get_logger
from .models import MediaItem, MediaType

log = get_logger(__name__)


class Identifier:
    def __init__(self, filters: FilterConfig):
        self.filters = filters
        self._exts = {e.lower().lstrip(".") for e in filters.video_extensions}
        self._exclude = [k.lower() for k in filters.exclude_keywords]

    def accept_file(self, path: Path) -> bool:
        """是否为候选媒体文件。"""
        if not path.is_file():
            return False
        if path.suffix.lstrip(".").lower() not in self._exts:
            return False
        name = path.name.lower()
        if any(k in name for k in self._exclude):
            log.debug("跳过(关键词命中): %s", path.name)
            return False
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError:
            return False
        if size_mb < self.filters.min_size_mb:
            log.debug("跳过(体积过小 %.1fMB): %s", size_mb, path.name)
            return False
        return True

    def identify(self, path: Path) -> Optional[MediaItem]:
        """解析单个文件，返回 MediaItem；无法识别返回 None。"""
        guess = dict(guessit(str(path.name)))
        gtype = guess.get("type")
        if gtype == "movie":
            media_type = MediaType.MOVIE
        elif gtype == "episode":
            media_type = MediaType.EPISODE
        else:
            media_type = MediaType.UNKNOWN

        title = guess.get("title")
        if not title:
            log.warning("无法解析标题: %s", path.name)
            return None

        season = guess.get("season")
        episode = guess.get("episode")
        # guessit 可能把多集解析成 list，取第一集
        if isinstance(episode, list):
            episode = episode[0] if episode else None
        if isinstance(season, list):
            season = season[0] if season else None
        # 有集号但无季号时默认第 1 季
        if media_type == MediaType.EPISODE and season is None and episode is not None:
            season = 1

        return MediaItem(
            source=path,
            media_type=media_type,
            title=str(title),
            year=guess.get("year"),
            season=season,
            episode=episode,
            raw=guess,
        )

    def identify_path_name(self, name: str) -> Optional[MediaItem]:
        """仅按文件名解析（不要求文件存在），便于测试与调试。"""
        return self.identify(Path(name))

    def scan_dir(self, root: Path) -> Iterator[MediaItem]:
        """递归扫描目录，产出可识别的 MediaItem。"""
        root = Path(root)
        if not root.exists():
            log.warning("源目录不存在: %s", root)
            return
        for path in sorted(root.rglob("*")):
            if not self.accept_file(path):
                continue
            item = self.identify(path)
            if item is not None:
                yield item

    def scan_dirs(self, roots: List[Path]) -> List[MediaItem]:
        items: List[MediaItem] = []
        for root in roots:
            items.extend(self.scan_dir(root))
        return items
