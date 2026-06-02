"""订阅集数去重 + 媒体服务器已拥有去重。"""

from pathlib import Path

from mediamaid.config import Config
from mediamaid.models import MediaItem, MediaType, Release
from mediamaid.plugins import Downloader, MediaServer, Subscriber, register
from mediamaid.store import StateStore
from mediamaid.subscribe import SubscribeRunner

# 每轮返回不同 guid 的同一集，验证按集去重（换源不重复抓）
_ROUND = {"n": 0}


@register
class _EpSub(Subscriber):
    name = "ep_sub_test"

    def fetch(self):
        _ROUND["n"] += 1
        return [Release(title=f"Show.Name.S01E01.1080p.WEB-r{_ROUND['n']}.mkv",
                        guid=f"g-{_ROUND['n']}", magnet="magnet:?x")]


_ADDED: list = []


@register
class _EpDl(Downloader):
    name = "ep_dl_test"

    def add(self, release: Release) -> bool:
        _ADDED.append(release.guid)
        return True


@register
class _OwnedMS(MediaServer):
    name = "owned_ms_test"

    def exists(self, item: MediaItem, info=None) -> bool:
        return True  # 谎称库里都已有


def _cfg(tmp_path: Path, plugins) -> Config:
    return Config(
        source_dirs=[tmp_path / "dl"],
        library_dir=tmp_path / "lib",
        state_db=tmp_path / "s.db",
        subscriptions=[{"id": "s1", "name": "剧", "subscriber": "ep_sub_test"}],
        plugins=plugins,
    )


def test_episode_dedup_across_rounds(tmp_path):
    _ADDED.clear()
    _ROUND["n"] = 0
    cfg = _cfg(tmp_path, {"downloader": [{"name": "ep_dl_test"}]})
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        assert runner.run_once() == 1          # 首轮抓到 S01E01
        assert runner.run_once() == 0          # 次轮换源同集 → 集数去重跳过
        assert len(_ADDED) == 1
        assert store.grabbed_count("s1") == 1


def test_skip_existing_via_mediaserver(tmp_path):
    _ADDED.clear()
    _ROUND["n"] = 0
    cfg = _cfg(
        tmp_path,
        {"downloader": [{"name": "ep_dl_test"}], "mediaserver": [{"name": "owned_ms_test"}]},
    )
    with StateStore(cfg.state_db) as store:
        runner = SubscribeRunner(cfg, store)
        # 媒体库已有 → 不下载
        assert runner.run_once() == 0
        assert _ADDED == []
