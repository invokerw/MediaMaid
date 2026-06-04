"""仪表盘、处理记录、扫描与订阅触发。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ...pipeline import Pipeline, build_notify
from ...subscribe import SubscribeRunner
from ..deps import WebContext, get_ctx
from ..logbuf import LOG_BUFFER
from ..schemas import RecordIdsBody, RecordStatusBody, ScanBody
from ..serializers import record_dict

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def api_dashboard(ctx: WebContext = Depends(get_ctx)):
    config = ctx.cfg()
    # 失败目录积压数
    failed_dir, failed_count = None, 0
    if config.failed_dir is not None:
        failed_dir = str(config.failed_dir)
        fd = Path(config.failed_dir)
        if fd.is_dir():
            failed_count = sum(1 for p in fd.rglob("*") if p.is_file())
    # 健康：是否配了 TMDB key
    spec = next((s for s in config.plugins.get("scraper", []) if s.name == "tmdb"), None)
    tmdb_key = bool(str((spec.config.get("api_key") if spec else "") or "").strip())
    return {
        "counts": ctx.store.counts(),
        "records": [record_dict(r) for r in ctx.store.recent(10)],
        "failed": {"dir": failed_dir, "count": failed_count},
        "health": {"tmdb_key": tmdb_key, "action": config.action.value},
        "subscriptions": len(config.subscriptions),
    }


@router.get("/records")
def api_records(status: Optional[str] = None, ctx: WebContext = Depends(get_ctx)):
    rows = ctx.store.recent(500)
    if status:
        rows = [r for r in rows if r.status == status]
    return {"records": [record_dict(r) for r in rows]}


@router.get("/logs")
def api_logs(limit: int = 200):
    """返回进程内日志缓冲（通知器/流水线），最新在前。"""
    return {"logs": LOG_BUFFER.tail(limit)}


@router.post("/records/delete")
def api_records_delete(body: RecordIdsBody, ctx: WebContext = Depends(get_ctx)):
    """批量删除记录。注意：删除 done 记录会解除去重，该源文件下次扫描会被重新整理。"""
    n = ctx.store.delete_many(body.ids)
    return {"deleted": n}


@router.post("/records/status")
def api_records_status(body: RecordStatusBody, ctx: WebContext = Depends(get_ctx)):
    """批量修改记录状态。"""
    if body.status not in ("done", "skipped", "failed"):
        raise HTTPException(422, "status 必须是 done / skipped / failed")
    n = ctx.store.set_status(body.ids, body.status)
    return {"updated": n}


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
