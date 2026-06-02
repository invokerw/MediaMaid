"""订阅过滤/择优：passes / score / best_per_episode / filter_and_pick。"""

import re

from mediamaid import subscribe_filter as sf
from mediamaid.config import SubscriptionFilter
from mediamaid.models import MediaType, ParseResult, Release


class _FakeId:
    """从标题用正则抽 SxxExx 作集号，模拟解析器链。"""

    def parse_name(self, name):
        m = re.search(r"[Ss](\d+)[Ee](\d+)", name)
        if m:
            return (
                ParseResult(
                    type=MediaType.EPISODE,
                    title="show",
                    season=int(m.group(1)),
                    episode=int(m.group(2)),
                ),
                "fake",
            )
        return None, None


def _rel(title, size=None, guid=None):
    return Release(title=title, guid=guid or title, size=size)


def test_passes_resolution():
    f = SubscriptionFilter(resolutions=["1080p", "2160p"])
    assert sf.passes(_rel("Show S01E01 1080p"), f)
    assert not sf.passes(_rel("Show S01E01 720p"), f)


def test_passes_include_exclude():
    f = SubscriptionFilter(include_keywords=["中字"], exclude_keywords=["HDTV"])
    assert sf.passes(_rel("Show 中字 1080p"), f)
    assert not sf.passes(_rel("Show 1080p"), f)          # 缺 include
    assert not sf.passes(_rel("Show 中字 HDTV"), f)       # 命中 exclude


def test_passes_include_exclude_regex():
    f = SubscriptionFilter(include_regex=r"S01E\d+", exclude_regex=r"720p|HDTV")
    assert sf.passes(_rel("Show S01E03 1080p"), f)
    assert not sf.passes(_rel("Show S02E03 1080p"), f)   # 不匹配 include
    assert not sf.passes(_rel("Show S01E03 720p"), f)    # 命中 exclude


def test_regex_is_case_insensitive():
    f = SubscriptionFilter(include_regex="中字", exclude_regex="hdtv")
    assert sf.passes(_rel("番剧 中字 1080P"), f)
    assert not sf.passes(_rel("番剧 中字 HDTV"), f)        # exclude 不区分大小写


def test_invalid_regex_falls_back_to_substring():
    # 非法正则（未闭合括号）退化为子串包含，不抛异常
    f = SubscriptionFilter(include_regex="(内封")
    assert sf.passes(_rel("Show (内封 字幕"), f)
    assert not sf.passes(_rel("Show 外挂"), f)


def test_passes_size_range():
    f = SubscriptionFilter(min_size_mb=500, max_size_mb=5000)
    mb = 1024 * 1024
    assert sf.passes(_rel("x", size=1000 * mb), f)
    assert not sf.passes(_rel("x", size=100 * mb), f)    # 太小
    assert not sf.passes(_rel("x", size=9000 * mb), f)   # 太大


def test_score_prefers_earlier_keyword():
    f = SubscriptionFilter(prefer=["2160p", "1080p"])
    assert sf.score(_rel("x 2160p"), f) > sf.score(_rel("x 1080p"), f)


def test_best_per_episode_picks_preferred():
    f = SubscriptionFilter(prefer=["2160p"])
    rels = [
        _rel("Show S01E01 1080p", guid="a"),
        _rel("Show S01E01 2160p", guid="b"),
    ]
    out = sf.best_per_episode(rels, _FakeId(), f)
    assert len(out) == 1 and out[0].guid == "b"


def test_best_per_episode_keeps_unparseable():
    # 电影/整季包解析不出集号 → 全部保留
    rels = [_rel("Some Movie 2020 1080p", guid="m1"), _rel("Another 2021", guid="m2")]
    out = sf.best_per_episode(rels, _FakeId())
    assert {r.guid for r in out} == {"m1", "m2"}


def test_filter_and_pick_combines():
    f = SubscriptionFilter(resolutions=["1080p", "2160p"], prefer=["2160p"])
    rels = [
        _rel("Show S01E01 720p", guid="lowres"),     # 被过滤
        _rel("Show S01E01 1080p", guid="a"),
        _rel("Show S01E01 2160p", guid="b"),          # 同集择优胜出
    ]
    out = sf.filter_and_pick(rels, f, _FakeId())
    assert len(out) == 1 and out[0].guid == "b"
