"""guessit 解析器：通用影视命名解析（默认）。"""

from __future__ import annotations

from typing import Optional

from guessit import guessit

from ...models import MediaType, ParseResult
from ..base import Parser
from ..registry import register


@register
class GuessitParser(Parser):
    name = "guessit"

    def parse(self, name: str) -> Optional[ParseResult]:
        guess = dict(guessit(name))
        title = guess.get("title")
        if not title:
            return None

        gtype = guess.get("type")
        if gtype == "movie":
            mt = MediaType.MOVIE
        elif gtype == "episode":
            mt = MediaType.EPISODE
        else:
            mt = MediaType.UNKNOWN

        season = guess.get("season")
        episode = guess.get("episode")
        if isinstance(episode, list):
            episode = episode[0] if episode else None
        if isinstance(season, list):
            season = season[0] if season else None
        if mt == MediaType.EPISODE and season is None and episode is not None:
            season = 1

        return ParseResult(
            type=mt,
            title=str(title),
            year=guess.get("year"),
            season=season,
            episode=episode,
            raw=guess,
        )
