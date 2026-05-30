"""配置加载与校验（pydantic + YAML）。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field

from .models import TransferAction


class FilterConfig(BaseModel):
    # 视频扩展名白名单
    video_extensions: List[str] = Field(
        default=["mkv", "mp4", "avi", "ts", "m2ts", "mov", "wmv", "flv", "iso"]
    )
    # 小于该体积(MB)的文件忽略（过滤 sample / 垃圾文件）
    min_size_mb: int = 50
    # 文件名包含这些关键词则跳过（不区分大小写）
    exclude_keywords: List[str] = Field(default=["sample", "trailer", "预告"])


class NamingConfig(BaseModel):
    # 模板可用占位符见 naming.py
    movie: str = "Movies/{title} ({year})/{title} ({year}).{ext}"
    episode: str = (
        "TV/{show} ({year})/Season {season:02d}/"
        "{show} - S{season:02d}E{episode:02d}.{ext}"
    )
    # 没有年份时的回退模板
    movie_no_year: str = "Movies/{title}/{title}.{ext}"
    episode_no_year: str = (
        "TV/{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}.{ext}"
    )


class ScraperConfig(BaseModel):
    enabled: bool = True
    tmdb_api_key: Optional[str] = None
    language: str = "zh-CN"
    # 标题相似度+年份匹配综合得分低于该值视为不可靠，不据此命名
    min_confidence: float = 0.5
    # 是否写 .nfo 与下载封面
    write_nfo: bool = False
    download_artwork: bool = False


class Config(BaseModel):
    # 监控/扫描的源目录（可多个）
    source_dirs: List[Path]
    # 媒体库根目录
    library_dir: Path
    # 默认落地方式
    action: TransferAction = TransferAction.HARDLINK
    # 同名目标已存在时：skip / overwrite / rename
    on_conflict: str = "skip"
    # 守护进程：文件大小连续 stable_seconds 秒不变才认为写入完成
    stable_seconds: int = 30
    # 守护进程：兜底全量重扫间隔（秒），0 表示关闭
    rescan_interval: int = 600
    # 状态库路径
    state_db: Path = Path("mediamaid.db")

    filters: FilterConfig = Field(default_factory=FilterConfig)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    scraper: ScraperConfig = Field(default_factory=ScraperConfig)


def load_config(path: Path) -> Config:
    """从 YAML 文件加载配置。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)
