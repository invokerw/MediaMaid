from pathlib import Path

from mediamaid.config import Config
from mediamaid.models import Release
from mediamaid.plugins import Downloader, Subscriber, register
from mediamaid.store import StateStore
from mediamaid.subscribe import SubscribeRunner


@register
class _FakeSub(Subscriber):
    name = "fake_sub_test"

    def fetch(self):
        return [
            Release(title="A 1080p", guid="g-a", magnet="magnet:?a"),
            Release(title="B 1080p", guid="g-b", magnet="magnet:?b"),
        ]


# 模块级记录被提交的下载，便于断言
_ADDED: list = []


@register
class _FakeDl(Downloader):
    name = "fake_dl_test"

    def add(self, release: Release) -> bool:
        _ADDED.append(release.guid)
        return True


def _cfg(tmp_path: Path) -> Config:
    return Config(
        source_dirs=[tmp_path / "dl"],
        library_dir=tmp_path / "lib",
        state_db=tmp_path / "s.db",
        subscriptions=[
            {"id": "s1", "name": "测试订阅", "subscriber": "fake_sub_test"},
        ],
        plugins={"downloader": [{"name": "fake_dl_test"}]},
    )


def test_subscribe_dispatch_and_dedup(tmp_path):
    _ADDED.clear()
    cfg = _cfg(tmp_path)
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        # 首轮：两条都提交
        assert runner.run_once() == 2
        assert sorted(_ADDED) == ["g-a", "g-b"]
        # 次轮：已 seen，去重，0 提交
        assert runner.run_once() == 0
        assert len(_ADDED) == 2
        # 按订阅 id 记录了已处理
        assert store.count_for("s1") == 2


# --- 订阅按 downloader 字段选定下载器 ---

_HITS: dict = {"one": [], "two": []}


@register
class _DlOne(Downloader):
    name = "dl_one_test"

    def add(self, release: Release) -> bool:
        _HITS["one"].append(release.guid)
        return True


@register
class _DlTwo(Downloader):
    name = "dl_two_test"

    def add(self, release: Release) -> bool:
        _HITS["two"].append(release.guid)
        return True


def _cfg_two_dl(tmp_path: Path, downloader=None) -> Config:
    sub = {"id": "s1", "name": "测试订阅", "subscriber": "fake_sub_test"}
    if downloader is not None:
        sub["downloader"] = downloader
    return Config(
        source_dirs=[tmp_path / "dl"],
        library_dir=tmp_path / "lib",
        state_db=tmp_path / "s.db",
        subscriptions=[sub],
        # dl_one 在前：若不按字段选定，遍历会命中 dl_one
        plugins={"downloader": [{"name": "dl_one_test"}, {"name": "dl_two_test"}]},
    )


def test_subscription_uses_selected_downloader(tmp_path):
    """订阅显式选定 dl_two：只提交到 dl_two，dl_one 不被调用。"""
    _HITS["one"].clear()
    _HITS["two"].clear()
    cfg = _cfg_two_dl(tmp_path, downloader="dl_two_test")
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        assert runner.run_once() == 2
        assert _HITS["one"] == []
        assert sorted(_HITS["two"]) == ["g-a", "g-b"]


def test_subscription_default_uses_first_downloader(tmp_path):
    """留空：沿用遍历逻辑，命中排在前的 dl_one。"""
    _HITS["one"].clear()
    _HITS["two"].clear()
    cfg = _cfg_two_dl(tmp_path, downloader=None)
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        assert runner.run_once() == 2
        assert sorted(_HITS["one"]) == ["g-a", "g-b"]
        assert _HITS["two"] == []


def test_subscription_unknown_downloader_skips(tmp_path):
    """指定了不存在/未启用的下载器：不静默回退，0 提交。"""
    _HITS["one"].clear()
    _HITS["two"].clear()
    cfg = _cfg_two_dl(tmp_path, downloader="does_not_exist")
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        assert runner.run_once() == 0
        assert _HITS["one"] == []
        assert _HITS["two"] == []
