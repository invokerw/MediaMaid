"""把领域对象序列化为前端 JSON 视图。"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..plugins import get as get_plugin
from ..store import Record, StateStore


def record_dict(r: Record) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "action": r.action,
        "src_path": r.src_path,
        "src_name": Path(r.src_path).name,
        "dst_path": r.dst_path,
        "dst_name": Path(r.dst_path).name if r.dst_path else None,
        "ts": r.ts,
    }


def settings_dict(config: Config) -> dict:
    """把当前配置序列化为前端可编辑的设置视图。"""
    return {
        "source_dirs": [str(p) for p in config.source_dirs],
        "library_dir": str(config.library_dir),
        "action": config.action.value,
        "on_conflict": config.on_conflict,
        "stable_seconds": config.stable_seconds,
        "rescan_interval": config.rescan_interval,
        "subscribe_interval": config.subscribe_interval,
        "poll_completed": config.poll_completed,
        "poll_interval": config.poll_interval,
        "write_nfo": config.write_nfo,
        "download_artwork": config.download_artwork,
        "anime_keywords": config.anime_keywords,
        "filters": {
            "video_extensions": config.filters.video_extensions,
            "min_size_mb": config.filters.min_size_mb,
            "exclude_keywords": config.filters.exclude_keywords,
        },
        "naming": {
            "movie": config.naming.movie,
            "episode": config.naming.episode,
            "movie_no_year": config.naming.movie_no_year,
            "episode_no_year": config.naming.episode_no_year,
            "anime": config.naming.anime,
            "anime_no_year": config.naming.anime_no_year,
        },
    }


def plugin_entry(config: Config, category: str, name: str) -> dict:
    """组装单个插件的 UI 信息：启停 + 当前配置 + 配置 schema。"""
    spec = next((s for s in config.plugins.get(category, []) if s.name == name), None)
    cls = get_plugin(category, name)
    return {
        "name": name,
        "description": cls.description,
        "enabled": bool(spec.enabled) if spec else False,
        "configured": spec is not None,
        "config": dict(spec.config) if spec else {},
        "schema": cls.ConfigModel.model_json_schema(),
    }


def release_dict(store: StateStore, rel) -> dict:
    return {
        "title": rel.title,
        "guid": rel.guid,
        "magnet": rel.magnet,
        "torrent_url": rel.torrent_url,
        "link": rel.link,
        "size": rel.size,
        "pub_date": rel.pub_date,
        "source": rel.source,
        "seen": store.release_seen(rel.guid),
    }


def sub_dict(store: StateStore, sub) -> dict:
    return {
        "id": sub.id,
        "name": sub.name,
        "subscriber": sub.subscriber,
        "enabled": sub.enabled,
        "downloader": sub.downloader,
        "config": dict(sub.config),
        "filters": sub.filters.model_dump(),
        "skip_existing": sub.skip_existing,
        "processed": store.count_for(sub.id),
        "grabbed_episodes": store.grabbed_count(sub.id),
    }


def download_task_dict(task) -> dict:
    """把 DownloadTask 序列化为前端 JSON（progress 保持 0~1，前端乘 100）。"""
    return {
        "id": task.id,
        "name": task.name,
        "downloader": task.downloader,
        "state": task.state,
        "progress": task.progress,
        "size": task.size,
        "downloaded": task.downloaded,
        "dl_speed": task.dl_speed,
        "up_speed": task.up_speed,
        "eta": task.eta,
        "error": task.error,
    }


def parser_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "parser": p.parser,
        "enabled": p.enabled,
        "config": dict(p.config),
    }
