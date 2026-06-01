"""识别：遍历源目录，用解析器链把文件名解析为 MediaItem。

解析器是插件（plugins/parser）。识别链按 config.parsers 顺序尝试，首个解析出
标题者胜出；链为空时回退内置 guessit，保持现有行为。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

from .config import Config, FilterConfig
from .logging_conf import get_logger
from .models import MediaItem, MediaType
from .plugins import Parser, create, load_plugins

log = get_logger(__name__)


def build_parsers(config: Config) -> List[Parser]:
    """按 config.parsers 顺序构建解析器链。

    自定义解析器按序在前；guessit 始终作为最后兜底（用户未显式配置 guessit 时自动追加），
    这样加了正则解析器也不会让普通命名失去通用解析。
    """
    load_plugins()
    chain: List[Parser] = []
    has_guessit = False
    for spec in config.enabled_parsers():
        try:
            chain.append(create("parser", spec.parser, spec.config))
            if spec.parser == "guessit":
                has_guessit = True
        except Exception as e:  # noqa: BLE001
            log.error("加载解析器 %s(%s) 失败: %s", spec.name, spec.parser, e)
    if not has_guessit:
        chain.append(create("parser", "guessit"))
    return chain


class Identifier:
    def __init__(self, config: Config):
        self.config = config
        self.filters: FilterConfig = config.filters
        self._exts = {e.lower().lstrip(".") for e in self.filters.video_extensions}
        self._exclude = [k.lower() for k in self.filters.exclude_keywords]
        self._anime_keywords = [k.lower() for k in config.anime_keywords if k]
        self.parsers = build_parsers(config)

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

    def parse_name(self, name: str):
        """对文件名跑解析器链，返回 (ParseResult, 命中的解析器名)；都不中→(None, None)。"""
        for parser in self.parsers:
            try:
                res = parser.parse(name)
            except Exception as e:  # noqa: BLE001
                log.warning("解析器 %s 异常 %s: %s", parser.name, name, e)
                continue
            if res is not None and res.title:
                return res, parser.name
        return None, None

    def _category(self, path: Path) -> str:
        """按 anime_keywords 命中源路径(含目录)则归为动漫，否则普通剧集。"""
        src = str(path).lower()
        if any(k in src for k in self._anime_keywords):
            return "anime"
        return "tv"

    def identify(self, path: Path) -> Optional[MediaItem]:
        """解析单个文件，返回 MediaItem；无法识别返回 None。"""
        res, _ = self.parse_name(path.name)
        if res is None:
            log.warning("无法解析: %s", path.name)
            return None
        return MediaItem(
            source=path,
            media_type=res.type,
            title=res.title,
            year=res.year,
            season=res.season,
            episode=res.episode,
            category=self._category(path),
            raw=res.raw,
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
