"""RSS 链接提取增强：enclosure / links 数组 / 带 query 种子 / 正文 magnet。"""

from mediamaid.plugins.subscriber.rss import _extract_links


def test_link_is_magnet():
    magnet, torrent = _extract_links({"link": "magnet:?xt=urn:btih:abc"})
    assert magnet == "magnet:?xt=urn:btih:abc" and torrent is None


def test_enclosure_torrent():
    entry = {"link": "http://site/detail",
             "enclosures": [{"href": "http://site/x.torrent", "type": "application/x-bittorrent"}]}
    magnet, torrent = _extract_links(entry)
    assert torrent == "http://site/x.torrent"


def test_torrent_with_query_token():
    # 不以 .torrent 结尾，但 type 表明是种子
    entry = {"link": "http://site/detail",
             "enclosures": [{"href": "http://site/dl?id=9&token=k", "type": "application/x-bittorrent"}]}
    magnet, torrent = _extract_links(entry)
    assert torrent == "http://site/dl?id=9&token=k"


def test_links_array_atom():
    entry = {"link": "http://site/detail",
             "links": [{"href": "http://site/a.torrent", "rel": "enclosure",
                        "type": "application/x-bittorrent"}]}
    magnet, torrent = _extract_links(entry)
    assert torrent == "http://site/a.torrent"


def test_magnet_in_summary_fallback():
    entry = {"link": "http://site/detail",
             "summary": "下载: magnet:?xt=urn:btih:deadbeef&dn=x 其它文字"}
    magnet, torrent = _extract_links(entry)
    assert magnet == "magnet:?xt=urn:btih:deadbeef&dn=x"


def test_no_links():
    magnet, torrent = _extract_links({"link": "http://site/detail-page"})
    assert magnet is None and torrent is None
