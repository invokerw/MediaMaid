"""生成 .nfo 元数据文件并下载封面/fanart（Kodi/Jellyfin 兼容）。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import httpx

from .logging_conf import get_logger
from .models import MediaInfo, MediaType

log = get_logger(__name__)


def _write_xml(root: ET.Element, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(dest, encoding="utf-8", xml_declaration=True)


def write_nfo(media_file: Path, info: MediaInfo, media_type: MediaType) -> Optional[Path]:
    """在媒体文件旁写同名 .nfo。"""
    if media_type == MediaType.MOVIE:
        root = ET.Element("movie")
        tag = "movie"
    elif media_type == MediaType.EPISODE:
        root = ET.Element("episodedetails")
        tag = "episodedetails"
    else:
        return None

    title = info.episode_title if (media_type == MediaType.EPISODE and info.episode_title) else info.title
    ET.SubElement(root, "title").text = title or info.title
    if info.year:
        ET.SubElement(root, "year").text = str(info.year)
    if info.overview:
        ET.SubElement(root, "plot").text = info.overview
    if info.tmdb_id:
        uid = ET.SubElement(root, "uniqueid", type="tmdb", default="true")
        uid.text = str(info.tmdb_id)
    if media_type == MediaType.EPISODE:
        if info.season is not None:
            ET.SubElement(root, "season").text = str(info.season)
        if info.episode is not None:
            ET.SubElement(root, "episode").text = str(info.episode)

    dest = media_file.with_suffix(".nfo")
    _write_xml(root, dest)
    log.debug("写入 nfo: %s (%s)", dest.name, tag)
    return dest


def download_artwork(media_file: Path, info: MediaInfo, media_type: MediaType) -> None:
    """下载封面/fanart 到媒体文件所在目录。"""
    targets = []
    if info.poster_url:
        targets.append((info.poster_url, media_file.with_name("poster.jpg")))
    if info.fanart_url:
        targets.append((info.fanart_url, media_file.with_name("fanart.jpg")))
    for url, dest in targets:
        if dest.exists():
            continue
        try:
            resp = httpx.get(url, timeout=30.0)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            log.debug("下载图片: %s", dest.name)
        except httpx.HTTPError as e:
            log.warning("下载图片失败 %s: %s", url, e)
