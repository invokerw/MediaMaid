"""状态库 grabbed_episodes 表读写。"""

from mediamaid.store import StateStore


def test_episode_grabbed_roundtrip(tmp_path):
    with StateStore(tmp_path / "s.db") as store:
        assert store.episode_grabbed("s1", "Show", 1, 1) is False
        store.mark_episode("s1", "Show", 1, 1, "guid-1")
        assert store.episode_grabbed("s1", "Show", 1, 1) is True
        # 大小写无关（show_key 归一化）
        assert store.episode_grabbed("s1", "show", 1, 1) is True
        # 不同集 / 不同订阅互不影响
        assert store.episode_grabbed("s1", "Show", 1, 2) is False
        assert store.episode_grabbed("s2", "Show", 1, 1) is False
        assert store.grabbed_count("s1") == 1


def test_mark_episode_idempotent(tmp_path):
    with StateStore(tmp_path / "s.db") as store:
        store.mark_episode("s1", "Show", 1, 1, "g1")
        store.mark_episode("s1", "Show", 1, 1, "g2")  # 同集重复写
        assert store.grabbed_count("s1") == 1
