"""订阅条目 CRUD、可见资源预览/历史、手动下载单条资源。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ...models import Release
from ...pipeline import Pipeline
from ...plugins import get as get_plugin
from ...subscribe import SubscribeRunner
from .. import cfgio
from ..deps import WebContext, get_ctx
from ..schemas import ReleaseBody, SubscriptionBody, SubscriptionUpdate
from ..serializers import release_dict, sub_dict

router = APIRouter(prefix="/api")


def _find_sub(ctx: WebContext, sub_id: str):
    sub = next((s for s in ctx.cfg().subscriptions if s.id == sub_id), None)
    if sub is None:
        raise HTTPException(404, f"订阅不存在: {sub_id}")
    return sub


@router.get("/subscriptions")
def api_subscriptions(ctx: WebContext = Depends(get_ctx)):
    return {"subscriptions": [sub_dict(ctx.store, s) for s in ctx.cfg().subscriptions]}


@router.post("/subscriptions")
def api_sub_create(body: SubscriptionBody, ctx: WebContext = Depends(get_ctx)):
    try:
        cls = get_plugin("subscriber", body.subscriber)
    except KeyError:
        raise HTTPException(404, f"未知订阅器: {body.subscriber}")
    try:
        cls.ConfigModel.model_validate(body.config)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    sub_id = uuid.uuid4().hex[:8]
    item = {
        "id": sub_id,
        "name": body.name,
        "subscriber": body.subscriber,
        "enabled": body.enabled,
        "config": body.config,
    }
    if body.downloader:
        item["downloader"] = body.downloader
    if body.filters is not None:
        item["filters"] = body.filters.model_dump(exclude_none=True)
    if body.skip_existing is not None:
        item["skip_existing"] = body.skip_existing
    cfgio.add_subscription(ctx.config_path, item)
    ctx.manager.reload()
    return sub_dict(ctx.store, _find_sub(ctx, sub_id))


@router.put("/subscriptions/{sub_id}")
def api_sub_update(sub_id: str, body: SubscriptionUpdate, ctx: WebContext = Depends(get_ctx)):
    sub = _find_sub(ctx, sub_id)
    subscriber = body.subscriber or sub.subscriber
    config = body.config if body.config is not None else sub.config
    try:
        cls = get_plugin("subscriber", subscriber)
        cls.ConfigModel.model_validate(config)
    except KeyError:
        raise HTTPException(404, f"未知订阅器: {subscriber}")
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    fields = body.model_dump(exclude_none=True)
    cfgio.update_subscription(ctx.config_path, sub_id, fields)
    ctx.manager.reload()
    return sub_dict(ctx.store, _find_sub(ctx, sub_id))


@router.delete("/subscriptions/{sub_id}")
def api_sub_delete(sub_id: str, ctx: WebContext = Depends(get_ctx)):
    _find_sub(ctx, sub_id)
    cfgio.delete_subscription(ctx.config_path, sub_id)
    ctx.manager.reload()
    return {"ok": True}


@router.get("/subscriptions/{sub_id}/preview")
async def api_sub_preview(sub_id: str, ctx: WebContext = Depends(get_ctx)):
    sub = _find_sub(ctx, sub_id)
    runner = SubscribeRunner(ctx.cfg(), ctx.store)
    releases = await run_in_threadpool(runner.preview, sub)
    return {"releases": [release_dict(ctx.store, r) for r in releases]}


@router.get("/subscriptions/{sub_id}/releases")
def api_sub_releases(sub_id: str, limit: int = 200, ctx: WebContext = Depends(get_ctx)):
    _find_sub(ctx, sub_id)
    return {
        "releases": [
            {"guid": g, "title": t, "ts": ts}
            for (g, t, ts) in ctx.store.releases_for(sub_id, limit)
        ]
    }


@router.post("/releases/download")
async def api_release_download(rel: ReleaseBody, ctx: WebContext = Depends(get_ctx)):
    config = ctx.cfg()
    runner = SubscribeRunner(config, ctx.store, notify=Pipeline(config, ctx.store).notify)
    if not runner.downloaders:
        raise HTTPException(400, "未配置下载器")
    release = Release(
        title=rel.title,
        guid=rel.guid,
        magnet=rel.magnet,
        torrent_url=rel.torrent_url,
        link=rel.link,
    )
    ok = await run_in_threadpool(runner.download_release, release, rel.sub_id)
    if not ok:
        raise HTTPException(502, "下载器未接受该资源")
    return {"ok": True}
