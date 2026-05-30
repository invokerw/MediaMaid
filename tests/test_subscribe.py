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
        plugins={
            "subscriber": [{"name": "fake_sub_test"}],
            "downloader": [{"name": "fake_dl_test"}],
        },
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
