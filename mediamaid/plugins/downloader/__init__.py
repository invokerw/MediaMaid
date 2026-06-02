"""下载器插件子包。"""

from __future__ import annotations

from typing import List, Tuple


class PathMapper:
    """跨容器/跨主机的下载路径映射（下载器视角路径 → MediaMaid 本地路径）。

    每条映射形如 "远端前缀:本地前缀"（如 "/downloads:/data/downloads"）。
    按远端前缀长度降序匹配（最长匹配优先）。qbittorrent/transmission/aria2 共用。
    """

    def __init__(self, mappings: List[str]):
        self._maps: List[Tuple[str, str]] = []
        for m in mappings or []:
            if ":" in m:
                remote, local = m.split(":", 1)
                if remote and local:
                    self._maps.append((remote.rstrip("/"), local.rstrip("/")))
        self._maps.sort(key=lambda x: len(x[0]), reverse=True)

    def map(self, p: str) -> str:
        for remote, local in self._maps:
            if p == remote or p.startswith(remote + "/"):
                return local + p[len(remote):]
        return p
