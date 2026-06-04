from mediamaid.config import Config, IgnoreEpisodes, TmdbRule
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


def _cfg(tmp_path, rules):
    return Config(
        source_dirs=[tmp_path], library_dir=tmp_path / "lib", tmdb_rules=rules
    )


def test_binding_rule_pins_tmdb_id(tmp_path):
    # 字幕组中文命名（guessit 难解析）→ 绑定规则直接钉到 tmdb_id，取季集
    cfg = _cfg(tmp_path, [
        TmdbRule(
            id="r1", tmdb_id=207468, title="遮天", media_type="episode", category="anime",
            patterns=[r"\]\[(?P<title>[^\]]*遮天[^\]]*)\].*\[(?P<episode>\d+)\]"],
            season=1,
        ),
    ])
    ident = Identifier(cfg)
    res, matched = ident.parse_name("[GM-Team][国漫][遮天][Shrouding the Heavens][2023][162].mkv")
    assert matched == "tmdb-binding"
    assert res.tmdb_id == 207468
    assert res.type == MediaType.EPISODE
    assert res.season == 1 and res.episode == 162
    assert res.category == "anime"
    assert res.title == ""  # 标题留给 TMDB


def test_binding_miss_falls_back_to_guessit(tmp_path):
    cfg = _cfg(tmp_path, [
        TmdbRule(id="r1", tmdb_id=1, patterns=[r"(?P<episode>NOMATCH)"]),
    ])
    ident = Identifier(cfg)
    res, matched = ident.parse_name("Breaking.Bad.S01E01.1080p.mkv")
    assert matched == "guessit"
    assert "Breaking Bad" in res.title
    assert res.tmdb_id is None


def test_no_rules_uses_guessit(tmp_path):
    cfg = _cfg(tmp_path, [])
    ident = Identifier(cfg)
    res, matched = ident.parse_name("The.Matrix.1999.1080p.mkv")
    assert matched == "guessit"
    assert "Matrix" in res.title


def test_identify_carries_tmdb_id_and_category(tmp_path):
    cfg = _cfg(tmp_path, [
        TmdbRule(id="r1", tmdb_id=99, media_type="episode", category="anime",
                 patterns=[r"FANSUB.*?(?P<episode>\d+)"], season=2),
    ])
    ident = Identifier(cfg)
    item = ident.identify(tmp_path / "FANSUB - 05.mkv")
    assert item.tmdb_id == 99 and item.season == 2 and item.episode == 5
    assert item.category == "anime"


def test_is_ignored(tmp_path):
    rules = [
        TmdbRule(id="r1", tmdb_id=42, ignore_seasons=[0],
                 ignore_episodes=[IgnoreEpisodes(season=1, episodes=[13, 14])]),
    ]
    cfg = _cfg(tmp_path, rules)
    assert cfg.is_ignored(42, 0, 1) is True          # 整季忽略
    assert cfg.is_ignored(42, 1, 13) is True          # 按季忽略具体集
    assert cfg.is_ignored(42, 1, 12) is False         # 未列入
    assert cfg.is_ignored(42, 2, 1) is False          # 其他季
    assert cfg.is_ignored(7, 0, 1) is False           # 其他 tmdb_id


def test_is_ignored_respects_enabled(tmp_path):
    cfg = _cfg(tmp_path, [
        TmdbRule(id="r1", tmdb_id=42, enabled=False, ignore_seasons=[0]),
    ])
    assert cfg.is_ignored(42, 0, 1) is False
