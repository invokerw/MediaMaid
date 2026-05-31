from pathlib import Path

from mediamaid.config import Config, ParserSpec
from mediamaid.identify import Identifier
from mediamaid.models import MediaType
from mediamaid.plugins import create, load_plugins


def test_guessit_parser():
    load_plugins()
    p = create("parser", "guessit")
    r = p.parse("Breaking.Bad.S03E07.720p.mkv")
    assert r.type == MediaType.EPISODE
    assert "Breaking Bad" in r.title
    assert r.season == 3 and r.episode == 7


def test_regex_parser_named_groups():
    load_plugins()
    p = create("parser", "regex", {"pattern": r"(?P<title>.+?)\.S(?P<season>\d+)E(?P<episode>\d+)"})
    r = p.parse("Some.Show.S02E05.1080p.mkv")
    assert r.type == MediaType.EPISODE
    assert r.title == "Some Show"
    assert r.season == 2 and r.episode == 5


def test_regex_parser_miss_returns_none():
    load_plugins()
    p = create("parser", "regex", {"pattern": r"(?P<title>NOPE)"})
    assert p.parse("whatever.mkv") is None


def _cfg(tmp_path, parsers):
    return Config(
        source_dirs=[tmp_path], library_dir=tmp_path / "lib", parsers=parsers
    )


def test_chain_first_match_wins(tmp_path):
    # 正则针对字幕组中文命名（guessit 解析不出），放在链首
    pat = r"\]\[(?P<title>[^\]]*遮天[^\]]*)\]"
    cfg = _cfg(tmp_path, [
        ParserSpec(id="r1", name="遮天", parser="regex", config={"pattern": pat, "type": "episode"}),
        ParserSpec(id="g", name="通用", parser="guessit"),
    ])
    ident = Identifier(cfg)
    res, matched = ident.parse_name("[GM-Team][国漫][遮天][Shrouding the Heavens][2023][162].mkv")
    assert matched == "regex"
    assert res.title == "遮天"


def test_chain_empty_falls_back_to_guessit(tmp_path):
    cfg = _cfg(tmp_path, [])
    ident = Identifier(cfg)
    res, matched = ident.parse_name("The.Matrix.1999.1080p.mkv")
    assert matched == "guessit"
    assert "Matrix" in res.title
