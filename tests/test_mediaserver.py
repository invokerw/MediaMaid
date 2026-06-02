"""媒体服务器 emby 插件：注册 + refresh/exists/test（monkeypatch 假 httpx）。"""

from pathlib import Path

import httpx

from mediamaid.models import MediaItem, MediaType
from mediamaid.plugins import available, create, load_plugins


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")


class _FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        if url.endswith("/System/Info"):
            return _Resp({"Version": "4.8", "ServerName": "Home"})
        if url.endswith("/Items"):
            return _Resp({"Items": [{"Name": "The Matrix", "ProductionYear": 1999}]})
        return _Resp({})

    def post(self, url, params=None):
        self.calls.append(("POST", url, params))
        return _Resp(None, 204)

    def close(self):
        pass


def _emby():
    load_plugins()
    inst = create("mediaserver", "emby", {"base_url": "http://h:8096/", "api_key": "k"})
    inst.client = _FakeClient()
    return inst


def _movie(title="The Matrix", year=1999):
    return MediaItem(source=Path("x.mkv"), media_type=MediaType.MOVIE, title=title, year=year)


def test_emby_registered():
    load_plugins()
    assert "emby" in available("mediaserver")


def test_emby_test_ok():
    inst = _emby()
    ok, msg = inst.test()
    assert ok and "Home" in msg


def test_emby_refresh_posts_library_refresh():
    inst = _emby()
    assert inst.refresh() is True
    assert any(c[0] == "POST" and c[1].endswith("/Library/Refresh") for c in inst.client.calls)


def test_emby_exists_movie_hit():
    inst = _emby()
    assert inst.exists(_movie()) is True


def test_emby_exists_year_mismatch():
    inst = _emby()
    assert inst.exists(_movie(year=2021)) is False


def test_emby_exists_title_mismatch():
    inst = _emby()
    assert inst.exists(_movie(title="完全不相关的片名")) is False
