"""RSS 订阅器：解析 RSS/Atom 源为 Release 列表。

依赖 feedparser（可选）。惰性 import，缺失时经 deps.require 自动安装。
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Release
from ..base import Subscriber
from ..deps import require
from ..registry import register

log = get_logger(__name__)


class RSSConfig(BaseModel):
    url: str
    timeout: float = 30.0


@register
class RSSSubscriber(Subscriber):
    name = "rss"
    description = "RSS/Atom 订阅器，解析订阅源为可下载的资源列表"
    ConfigModel = RSSConfig

    def test(self):
        try:
            releases = self.fetch()
        except Exception as e:  # noqa: BLE001
            return False, f"RSS 抓取失败: {e}"
        return True, f"RSS 可达，抓取到 {len(releases)} 条"

    def fetch(self) -> List[Release]:
        feedparser, err = require("feedparser")  # 缺失则自动安装
        if feedparser is None:
            # 调用方（subscribe / test）均已 try/except，抛出以回显真实原因
            raise RuntimeError(err)

        cfg: RSSConfig = self.config
        feed = feedparser.parse(cfg.url)
        if getattr(feed, "bozo", False):
            log.warning("RSS 解析告警 %s: %s", cfg.url, getattr(feed, "bozo_exception", ""))

        releases: List[Release] = []
        for entry in feed.entries:
            title = entry.get("title", "")
            magnet, torrent_url = _extract_links(entry)
            guid = entry.get("id") or entry.get("link") or title
            releases.append(
                Release(
                    title=title,
                    guid=guid,
                    magnet=magnet,
                    torrent_url=torrent_url,
                    link=entry.get("link"),
                    size=_extract_size(entry),
                    pub_date=entry.get("published"),
                    source=f"rss:{cfg.url}",
                )
            )
        log.info("RSS 抓取到 %d 条: %s", len(releases), cfg.url)
        return releases


_MAGNET_RE = re.compile(r"magnet:\?xt=urn:[^\s\"'<>]+")


def _is_torrent(href: str, mimetype: str) -> bool:
    """判定一个链接是否指向种子（兼容带 query/token 的下载链接）。"""
    if not href:
        return False
    if mimetype in ("application/x-bittorrent", "application/x-torrent"):
        return True
    if href.endswith(".torrent"):
        return True
    # 带 query 的下载链接：路径段含 .torrent 或常见下载路径
    path = href.split("?", 1)[0].lower()
    return path.endswith(".torrent") or "/download" in path or "/torrent" in path


def _extract_links(entry) -> tuple[Optional[str], Optional[str]]:
    link = entry.get("link", "") or ""
    if link.startswith("magnet:"):
        return link, None
    magnet = None
    torrent_url = None

    # 1. enclosures（标准 RSS 种子分发位）
    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href", "") or enc.get("url", "")
        mime = enc.get("type", "") or ""
        if href.startswith("magnet:"):
            magnet = magnet or href
        elif _is_torrent(href, mime):
            torrent_url = torrent_url or href

    # 2. links 数组（Atom：rel=enclosure / type=application/x-bittorrent）
    for lk in entry.get("links", []) or []:
        href = lk.get("href", "") or ""
        mime = lk.get("type", "") or ""
        if href.startswith("magnet:"):
            magnet = magnet or href
        elif lk.get("rel") == "enclosure" and _is_torrent(href, mime):
            torrent_url = torrent_url or href

    # 3. link 本身是种子下载链接
    if not torrent_url and _is_torrent(link, ""):
        torrent_url = link

    # 4. 兜底：从正文/摘要里正则抓 magnet
    if not magnet:
        text = " ".join(
            str(entry.get(k, "")) for k in ("summary", "description", "title")
        )
        m = _MAGNET_RE.search(text)
        if m:
            magnet = m.group(0)

    return magnet, torrent_url


def _extract_size(entry) -> Optional[int]:
    for enc in entry.get("enclosures", []) or []:
        length = enc.get("length")
        if length and str(length).isdigit():
            return int(length)
    return None
