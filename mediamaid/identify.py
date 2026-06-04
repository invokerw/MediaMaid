"""识别：遍历源目录，用解析器链把文件名解析为 MediaItem。

链首是 TMDB 绑定解析器（命中规则正则 → 直接钉到某 tmdb_id），其后是内置 guessit
兜底（按标题解析，留给后续 TMDB 搜索）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List, Optional

from .config import Config, FilterConfig, TmdbRule
from .logging_conf import get_logger
from .models import MediaItem, MediaType, ParseResult
from .plugins import Parser, create, load_plugins

log = get_logger(__name__)


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


class TmdbBindingParser:
    """TMDB 绑定解析器：命中规则的某个正则 → 直接产出带 tmdb_id 的 ParseResult。

    不走 registry（由 config.tmdb_rules 构造，非用户可插拔的插件实例），鸭子类型即可。
    """

    name = "tmdb-binding"

    def __init__(self, rules: List[TmdbRule]):
        # 预编译每条规则的正则（非法的跳过并告警）
        self._compiled = []
        for rule in rules:
            pats = []
            for p in rule.patterns:
                try:
                    pats.append(re.compile(p))
                except re.error as e:
                    log.error("TMDB 规则 %s 正则编译失败 %r: %s", rule.tmdb_id, p, e)
            if pats:
                self._compiled.append((rule, pats))

    def parse(self, name: str) -> Optional[ParseResult]:
        for rule, pats in self._compiled:
            for rx in pats:
                m = rx.search(name)
                if not m:
                    continue
                groups = m.groupdict()
                mt = MediaType.MOVIE if rule.media_type == "movie" else MediaType.EPISODE
                season = rule.season if rule.season is not None else _to_int(groups.get("season"))
                episode = _to_int(groups.get("episode"))
                if mt == MediaType.EPISODE and season is None and episode is not None:
                    season = 1
                return ParseResult(
                    type=mt,
                    title="",  # 标题来自 TMDB（fetch_by_id），此处留空
                    tmdb_id=rule.tmdb_id,
                    season=season,
                    episode=episode,
                    category=rule.category,
                    raw=groups,
                )
        return None


def build_parsers(config: Config):
    """构建解析器链：TMDB 绑定解析器（若有规则）在前，guessit 兜底在后。"""
    load_plugins()
    chain = []
    rules = [r for r in config.enabled_tmdb_rules() if r.patterns]
    if rules:
        chain.append(TmdbBindingParser(rules))
    chain.append(create("parser", "guessit"))
    return chain


class Identifier:
    def __init__(self, config: Config):
        self.config = config
        self.filters: FilterConfig = config.filters
        self._exts = {e.lower().lstrip(".") for e in self.filters.video_extensions}
        self._anime_keywords = [k.lower() for k in config.anime_keywords if k]
        self.parsers = build_parsers(config)

    def accept_file(self, path: Path) -> bool:
        """是否为候选媒体文件。"""
        if not path.is_file():
            return False
        if path.suffix.lstrip(".").lower() not in self._exts:
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
            # 接受：解析出标题，或绑定规则给出了 tmdb_id（标题留给 TMDB）
            if res is not None and (res.title or res.tmdb_id):
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
            tmdb_id=res.tmdb_id,
            # 绑定规则可指定分类（tv/anime）；否则按源路径关键词判定
            category=res.category or self._category(path),
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
            # 失败目录里的文件不自动处理（可能位于某源目录内）
            if self.config.under_failed(path):
                continue
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

    def accepted_paths(self, roots: List[Path]) -> List[Path]:
        """递归列出通过过滤的候选文件路径（排除失败目录），不做识别。

        供流水线统一路由：识别成功→整理；识别失败→（可选）隔离到失败目录。
        """
        out: List[Path] = []
        for root in roots:
            root = Path(root)
            if not root.exists():
                log.warning("源目录不存在: %s", root)
                continue
            for path in sorted(root.rglob("*")):
                if self.config.under_failed(path):
                    continue
                if self.accept_file(path):
                    out.append(path)
        return out
