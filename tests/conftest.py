"""测试公共夹具。

刮削器固定为 TMDB 且缺 api_key 会报错；测试不应联网刮削，故默认把
`pipeline.build_scrapers` 替换为一个返回 None 的桩刮削器——等价于过去的
noscrape 行为（仅按文件名整理），让各测试无需配置真实 TMDB key。

需要验证「真实 build_scrapers 行为」的测试，请在模块顶层
`from mediamaid.pipeline import build_scrapers` 直接引用（该绑定指向原函数，
不受本夹具对模块属性的替换影响）。
"""

import pytest


class _StubScraper:
    name = "stub"

    def scrape(self, item):
        return None

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _stub_scrapers(monkeypatch):
    monkeypatch.setattr(
        "mediamaid.pipeline.build_scrapers", lambda config: [_StubScraper()]
    )
