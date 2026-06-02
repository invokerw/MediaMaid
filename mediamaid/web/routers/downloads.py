"""下载管理：聚合各下载器的任务列表，支持取消/暂停/恢复/手动新建。

下载器实例由 WebContext.downloaders() 缓存复用（轮询频繁，避免每次重连）。
仅 supports_management=True 的下载器提供任务查询与控制能力。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ...plugins import get as get_plugin
from ..deps import WebContext, get_ctx
from ..schemas import NewDownloadBody
from ..serializers import download_task_dict

router = APIRouter(prefix="/api")


@router.get("/downloaders")
def api_downloaders(ctx: WebContext = Depends(get_ctx)):
    """列出已配置（启用）的下载器，供订阅等处下拉选用。不连接、不查任务。"""
    out = []
    for spec in ctx.cfg().plugin_specs("downloader"):
        try:
            cls = get_plugin("downloader", spec.name)
            desc = getattr(cls, "description", "") or ""
        except KeyError:
            desc = ""
        out.append({"name": spec.name, "description": desc})
    return {"downloaders": out}


@router.get("/downloads")
async def api_downloads(ctx: WebContext = Depends(get_ctx)):
    downloaders = ctx.downloaders()

    def collect():
        tasks = []
        for d in downloaders:
            if not d.supports_management:
                continue
            for t in d.list_tasks():
                t.downloader = d.name
                tasks.append(download_task_dict(t))
        return tasks

    tasks = await run_in_threadpool(collect)
    return {
        "downloaders": [
            {"name": d.name, "supports_management": d.supports_management}
            for d in downloaders
        ],
        "tasks": tasks,
    }


@router.post("/downloads")
async def api_download_create(body: NewDownloadBody, ctx: WebContext = Depends(get_ctx)):
    d = ctx.downloader(body.downloader)
    if not body.uri.strip():
        raise HTTPException(422, "下载链接不能为空")
    ok = await run_in_threadpool(d.add_uri, body.uri.strip(), body.save_path)
    if not ok:
        raise HTTPException(502, "下载器未接受该链接")
    return {"ok": True}


@router.delete("/downloads/{name}/{task_id}")
async def api_download_remove(
    name: str, task_id: str, delete_files: bool = False, ctx: WebContext = Depends(get_ctx)
):
    d = ctx.downloader(name)
    ok = await run_in_threadpool(d.remove, task_id, delete_files)
    if not ok:
        raise HTTPException(502, "取消任务失败")
    return {"ok": True}


@router.post("/downloads/{name}/{task_id}/pause")
async def api_download_pause(name: str, task_id: str, ctx: WebContext = Depends(get_ctx)):
    d = ctx.downloader(name)
    ok = await run_in_threadpool(d.pause, task_id)
    if not ok:
        raise HTTPException(502, "暂停任务失败")
    return {"ok": True}


@router.post("/downloads/{name}/{task_id}/resume")
async def api_download_resume(name: str, task_id: str, ctx: WebContext = Depends(get_ctx)):
    d = ctx.downloader(name)
    ok = await run_in_threadpool(d.resume, task_id)
    if not ok:
        raise HTTPException(502, "恢复任务失败")
    return {"ok": True}
