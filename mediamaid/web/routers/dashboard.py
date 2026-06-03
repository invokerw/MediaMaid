"""仪表盘、处理记录、扫描与订阅触发。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ...pipeline import Pipeline, build_notify
from ...subscribe import SubscribeRunner
from ..deps import WebContext, get_ctx
from ..schemas import ScanBody
from ..serializers import record_dict

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def api_dashboard(ctx: WebContext = Depends(get_ctx)):
    return {
        "counts": ctx.store.counts(),
        "records": [record_dict(r) for r in ctx.store.recent(10)],
    }


@router.get("/records")
def api_records(status: Optional[str] = None, ctx: WebContext = Depends(get_ctx)):
    rows = ctx.store.recent(500)
    if status:
        rows = [r for r in rows if r.status == status]
    return {"records": [record_dict(r) for r in rows]}


@router.post("/scan")
async def api_scan(body: ScanBody, ctx: WebContext = Depends(get_ctx)):
    try:
        pipeline = Pipeline(ctx.cfg(), ctx.store)
    except RuntimeError as e:  # 未配置 TMDB api_key 等
        raise HTTPException(400, str(e))
    results = await run_in_threadpool(pipeline.scan, body.dry_run)
    summary: dict = {}
    items = []
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
        items.append(
            {
                "source": r.item.source.name,
                "status": r.status,
                "dest": str(r.dest) if r.dest else None,
            }
        )
    return {"dry_run": body.dry_run, "summary": summary, "items": items}


@router.post("/subscribe")
async def api_subscribe(ctx: WebContext = Depends(get_ctx)):
    config = ctx.cfg()
    runner = SubscribeRunner(config, ctx.store, notify=build_notify(config))
    submitted = await run_in_threadpool(runner.run_once)
    return {"submitted": submitted}
