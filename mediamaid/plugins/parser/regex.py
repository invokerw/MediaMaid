"""正则解析器：用命名组从文件名提取字段，供用户自定义。

pattern 用 Python 命名组：
  (?P<title>...) (?P<year>\\d{4}) (?P<season>\\d+) (?P<episode>\\d+)
示例（字幕组动漫）：\\[.*?\\]\\[.*?\\]\\[(?P<title>[^\\]]+)\\].*?\\[(?P<episode>\\d+)
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import MediaType, ParseResult
from ..base import Parser
from ..registry import register

log = get_logger(__name__)


class RegexConfig(BaseModel):
    pattern: str
    # auto: 有 episode 组→剧集，否则电影；也可强制 movie/episode
    type: str = "auto"


def _to_int(v):
    if v is None:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def _clean_title(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace(".", " ").replace("_", " ")).strip()


@register
class RegexParser(Parser):
    name = "regex"
    ConfigModel = RegexConfig

    def __init__(self, config: RegexConfig):
        super().__init__(config)
        try:
            self._re = re.compile(config.pattern)
        except re.error as e:
            log.error("正则编译失败 %r: %s", config.pattern, e)
            self._re = None

    def parse(self, name: str) -> Optional[ParseResult]:
        if self._re is None:
            return None
        m = self._re.search(name)
        if not m:
            return None
        groups = m.groupdict()
        title = groups.get("title")
        if not title:
            return None
        episode = _to_int(groups.get("episode"))
        season = _to_int(groups.get("season"))
        year = _to_int(groups.get("year"))

        cfg: RegexConfig = self.config
        if cfg.type == "movie":
            mt = MediaType.MOVIE
        elif cfg.type == "episode":
            mt = MediaType.EPISODE
        else:
            mt = MediaType.EPISODE if episode is not None else MediaType.MOVIE
        if mt == MediaType.EPISODE and season is None and episode is not None:
            season = 1

        return ParseResult(
            type=mt,
            title=_clean_title(title),
            year=year,
            season=season,
            episode=episode,
            raw=groups,
        )
