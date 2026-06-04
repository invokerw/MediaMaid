"""单文件识别预览 + 手动转移（按用户指定的 TMDB 条目刮削落地）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ...identify import Identifier
from ...models import MediaInfo, MediaItem, MediaType
from ...organizer import Organizer
from ...pipeline import Pipeline, build_scrapers
from ..deps import WebContext, get_ctx, _is_within, safe_path
from ..schemas import OrganizeIdentifyBody, OrganizeManualBody

router = APIRouter(prefix="/api/organize")


def _source_path(ctx: WebContext, path_str: str) -> Path:
    """校验路径在受管根内，且位于源目录或失败目录（不允许媒体库内文件）。"""
    p = safe_path(ctx, path_str)
    cfg = ctx.cfg()
    allowed = list(cfg.source_dirs)
    if cfg.failed_dir is not None:
        allowed.append(cfg.failed_dir)
    roots = []
    for s in allowed:
        try:
            roots.append(Path(s).resolve())
        except OSError:
            continue
    if not any(p == s or _is_within(p, s) for s in roots):
        raise HTTPException(400, "只能对源目录/失败目录中的文件执行该操作")
    if not p.is_file():
        raise HTTPException(404, "文件不存在")
    return p


def _media_type(value: str) -> MediaType:
    try:
        mt = MediaType(value)
    except ValueError:
        raise HTTPException(422, f"未知媒体类型: {value}")
    if mt not in (MediaType.MOVIE, MediaType.EPISODE):
        raise HTTPException(422, "media_type 必须是 movie 或 episode")
    return mt


def _parsed_dict(item: Optional[MediaItem]) -> Optional[dict]:
    if item is None:
        return None
    return {
        "title": item.title,
        "year": item.year,
        "season": item.season,
        "episode": item.episode,
        "media_type": item.media_type.value,
        "category": item.category,
    }


def _matched_dict(info: Optional[MediaInfo]) -> Optional[dict]:
    if info is None:
        return None
    return {
        "title": info.title,
        "year": info.year,
        "tmdb_id": info.tmdb_id,
        "season": info.season,
        "episode": info.episode,
        "episode_title": info.episode_title,
        "confidence": info.confidence,
        "poster_url": info.poster_url,
    }


@router.post("/identify")
async def api_identify(body: OrganizeIdentifyBody, ctx: WebContext = Depends(get_ctx)):
    """识别 + TMDB 自动搜索预览（不落地）。无 key 时仅返回解析结果。"""
    p = _source_path(ctx, body.path)
    cfg = ctx.cfg()

    def _run():
        item = Identifier(cfg).identify(p)
        matched = None
        has_key = True
        if item is not None:
            try:
                scraper = build_scrapers(cfg)[0]
            except RuntimeError:
                has_key = False
                scraper = None
            if scraper is not None:
                try:
                    matched = scraper.scrape(item)
                finally:
                    scraper.close()
        dest_preview = None
        if item is not None:
            try:
                dest_preview = str(Organizer(cfg).plan(item, matched).dest)
            except Exception:  # noqa: BLE001 - 预览失败不致命
                dest_preview = None
        return {
            "parsed": _parsed_dict(item),
            "matched": _matched_dict(matched),
            "has_key": has_key,
            "dest_preview": dest_preview,
        }

    return await run_in_threadpool(_run)


@router.get("/tmdb-preview")
async def api_tmdb_preview(
    tmdb_id: int,
    media_type: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    ctx: WebContext = Depends(get_ctx),
):
    """按 TMDB ID 预览条目信息（供手动转移弹窗确认）。"""
    mt = _media_type(media_type)
    cfg = ctx.cfg()

    def _run():
        try:
            scraper = build_scrapers(cfg)[0]
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        try:
            info = scraper.fetch_by_id(mt, tmdb_id, season, episode)
        finally:
            scraper.close()
        if info is None:
            raise HTTPException(404, "TMDB 未找到该条目")
        # 用预览信息构造一个临时 item 算目标路径
        item = MediaItem(
            source=Path("preview.mkv"),
            media_type=mt,
            title=info.title,
            year=info.year,
            season=season,
            episode=episode,
            category="tv",
        )
        dest_preview = str(Organizer(cfg).plan(item, info).dest)
        return {
            "title": info.title,
            "year": info.year,
            "episode_title": info.episode_title,
            "dest_preview": dest_preview,
        }

    return await run_in_threadpool(_run)


@router.post("/manual")
async def api_manual(body: OrganizeManualBody, ctx: WebContext = Depends(get_ctx)):
    """手动转移：按指定 TMDB 条目刮削落地；已转移则先撤销旧目标。"""
    p = _source_path(ctx, body.path)
    mt = _media_type(body.media_type)
    cfg = ctx.cfg()

    def _run():
        try:
            pipeline = Pipeline(cfg, ctx.store)
        except RuntimeError as e:  # 缺 TMDB key
            raise HTTPException(400, str(e))
        info = pipeline.scrapers[0].fetch_by_id(mt, body.tmdb_id, body.season, body.episode)
        if info is None:
            raise HTTPException(404, "TMDB 未找到该条目")
        item = MediaItem(
            source=p,
            media_type=mt,
            title=info.title or p.stem,
            year=info.year,
            season=body.season,
            episode=body.episode,
            category=(body.category or "tv") if mt == MediaType.EPISODE else "tv",
        )
        # 覆盖式纠正：先落新位置，成功后再清旧目标（见 organize_manual）
        result = pipeline.organize_manual(item, info)
        return {
            "status": result.status,
            "dest": str(result.dest) if result.dest else None,
            "error": result.error,
        }

    return await run_in_threadpool(_run)
