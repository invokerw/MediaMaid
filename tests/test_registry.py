import pytest

from mediamaid import plugins
from mediamaid.models import Event
from mediamaid.plugins import Notifier, available, create, load_plugins, register
from mediamaid.plugins.base import Scraper


def test_load_plugins_discovers_builtins():
    load_plugins()
    assert "tmdb" in available("scraper")
    assert "rss" in available("subscriber")
    assert "qbittorrent" in available("downloader")
    assert "log" in available("notifier")
    assert "webhook" in available("notifier")


def test_create_with_config_validation():
    load_plugins()
    # tmdb 需要 api_key，缺失应校验失败
    with pytest.raises(Exception):
        create("scraper", "tmdb", {})
    sc = create("scraper", "tmdb", {"api_key": "x", "language": "en-US"})
    assert sc.name == "tmdb"
    assert sc.config.language == "en-US"


def test_register_rejects_bad_category():
    with pytest.raises(ValueError):
        @register
        class Bad(Scraper):
            category = "nope"
            name = "bad"

            def scrape(self, item):
                return None


def test_register_and_create_custom_notifier():
    captured = []

    @register
    class MemNotifier(Notifier):
        name = "mem_test"

        def notify(self, event: Event) -> None:
            captured.append(event.message)

    assert "mem_test" in available("notifier")
    n = create("notifier", "mem_test")
    n.notify(Event("info", "hello"))
    assert captured == ["hello"]


def test_get_unknown_raises():
    load_plugins()
    with pytest.raises(KeyError):
        plugins.get("scraper", "does_not_exist")
