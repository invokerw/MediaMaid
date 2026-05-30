"""媒体库命名：根据模板把 MediaItem/MediaInfo 渲染成目标相对路径。

默认遵循 Jellyfin/Plex 命名规范。模板占位符：
  电影:  {title} {year} {ext}
  剧集:  {show} {year} {season} {episode} {episode_title} {ext}
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .config import NamingConfig
from .models import MediaInfo, MediaItem, MediaType

# 文件名中的非法/危险字符
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str) -> str:
    """清洗用于文件名的字符串。"""
    name = _ILLEGAL.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    # 去掉结尾的点和空格（Windows 不允许）
    return name.rstrip(". ")


def _merge(item: MediaItem, info: Optional[MediaInfo]) -> dict:
    """合并解析结果与刮削结果，刮削结果优先。"""
    title = (info.title if info and info.title else item.title) or "Unknown"
    year = (info.year if info and info.year else item.year)
    season = item.season if item.season is not None else (info.season if info else None)
    episode = (
        item.episode if item.episode is not None else (info.episode if info else None)
    )
    episode_title = info.episode_title if info else None
    return {
        "title": sanitize(title),
        "show": sanitize(title),
        "year": year or "",
        "season": season if season is not None else 0,
        "episode": episode if episode is not None else 0,
        "episode_title": sanitize(episode_title) if episode_title else "",
        "ext": item.ext,
    }


def render_dest(
    item: MediaItem,
    info: Optional[MediaInfo],
    config: NamingConfig,
) -> Path:
    """返回相对于媒体库根目录的目标路径。"""
    fields = _merge(item, info)

    if item.media_type == MediaType.MOVIE:
        template = config.movie if fields["year"] else config.movie_no_year
    elif item.media_type == MediaType.EPISODE:
        template = config.episode if fields["year"] else config.episode_no_year
    else:
        raise ValueError(f"无法为未知类型生成路径: {item.source}")

    rel = template.format(**fields)
    # 逐段清洗，避免模板里固定文本被破坏
    parts = [sanitize(p) for p in Path(rel).parts]
    return Path(*parts)
