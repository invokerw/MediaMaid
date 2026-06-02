"""标题匹配增强：相等/包含/标点归一化。"""

from mediamaid.plugins.scraper import score_match, title_similarity


def test_exact_after_normalization():
    # 标点/大小写差异归一化后视为相等
    assert title_similarity("The Matrix", "the matrix!") == 1.0
    assert title_similarity("钢铁侠2", "钢铁侠2！") == 1.0


def test_containment_boost():
    # 短标题完整包含于长标题（"遮天" ⊂ "遮天 第一季"）应得较高分
    s = title_similarity("遮天", "遮天 第一季")
    assert s >= 0.6


def test_too_short_substring_not_over_boosted():
    # 单字符不触发包含加权，避免误命中
    s = title_similarity("天", "遮天 第一季")
    assert s < 0.6


def test_score_match_year_bonus():
    # 同名同年 > 同名错年
    same = score_match("The Matrix", 1999, "The Matrix", 1999)
    wrong = score_match("The Matrix", 1999, "The Matrix", 2003)
    assert same > wrong
