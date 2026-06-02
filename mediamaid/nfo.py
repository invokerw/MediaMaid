"""生成 .nfo 元数据文件并下载封面/fanart（Kodi/Jellyfin/Emby 兼容）。"""

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


def _add_common(root: ET.Element, info: MediaInfo) -> None:
    """写通用的 genre / rating / 外部 ID 节点（tmdb/imdb/tvdb）。"""
    for g in info.genres or []:
        ET.SubElement(root, "genre").text = g
    if info.rating:
        ET.SubElement(root, "rating").text = f"{info.rating:.1f}"
    if info.tmdb_id:
        uid = ET.SubElement(root, "uniqueid", type="tmdb", default="true")
        uid.text = str(info.tmdb_id)
    if info.imdb_id:
        ET.SubElement(root, "uniqueid", type="imdb").text = str(info.imdb_id)
    if info.tvdb_id:
        ET.SubElement(root, "uniqueid", type="tvdb").text = str(info.tvdb_id)


def write_nfo(media_file: Path, info: MediaInfo, media_type: MediaType) -> Optional[Path]:
    """在媒体文件旁写同名 .nfo。"""
    if media_type == MediaType.MOVIE:
        root = ET.Element("movie")
    elif media_type == MediaType.EPISODE:
        root = ET.Element("episodedetails")
    else:
        return None

    title = info.episode_title if (media_type == MediaType.EPISODE and info.episode_title) else info.title
    ET.SubElement(root, "title").text = title or info.title
    if info.year:
        ET.SubElement(root, "year").text = str(info.year)
    if info.overview:
        ET.SubElement(root, "plot").text = info.overview
    if media_type == MediaType.EPISODE:
        if info.season is not None:
            ET.SubElement(root, "season").text = str(info.season)
        if info.episode is not None:
            ET.SubElement(root, "episode").text = str(info.episode)
    _add_common(root, info)

    dest = media_file.with_suffix(".nfo")
    _write_xml(root, dest)
    log.debug("写入 nfo: %s", dest.name)
    return dest


def write_tvshow_nfo(series_root: Path, info: MediaInfo) -> Optional[Path]:
    """在剧集根目录写 tvshow.nfo（媒体服务器识别整部剧的关键文件）。已存在则不覆盖。"""
    dest = series_root / "tvshow.nfo"
    if dest.exists():
        return dest
    root = ET.Element("tvshow")
    ET.SubElement(root, "title").text = info.title
    if info.year:
        ET.SubElement(root, "year").text = str(info.year)
    if info.overview:
        ET.SubElement(root, "plot").text = info.overview
    _add_common(root, info)
    _write_xml(root, dest)
    log.debug("写入 tvshow.nfo: %s", dest)
    return dest


def _download_image(url: str, dest: Path, client: Optional[httpx.Client]) -> None:
    if dest.exists():
        return
    try:
        if client is not None:
            resp = client.get(url)
        else:
            resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        log.debug("下载图片: %s", dest.name)
    except httpx.HTTPError as e:
        log.warning("下载图片失败 %s: %s", url, e)


def download_artwork(
    media_file: Path,
    info: MediaInfo,
    media_type: MediaType,
    client: Optional[httpx.Client] = None,
) -> None:
    """下载封面/fanart。

    电影：poster.jpg / fanart.jpg 放在影片所在目录。
    剧集：poster.jpg / fanart.jpg 放在剧集根目录（season 上一级），供整部剧识别。
    """
    if media_type == MediaType.EPISODE:
        art_dir = media_file.parent.parent  # 剧集根（Season XX 的上一级）
    else:
        art_dir = media_file.parent
    if info.poster_url:
        _download_image(info.poster_url, art_dir / "poster.jpg", client)
    if info.fanart_url:
        _download_image(info.fanart_url, art_dir / "fanart.jpg", client)
