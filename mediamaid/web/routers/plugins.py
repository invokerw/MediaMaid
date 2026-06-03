"""插件列表/启停/连接测试，以及订阅器、解析器类型 + schema。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ...plugins import CATEGORIES, available, get as get_plugin
from .. import cfgio
from ..deps import WebContext, get_ctx
from ..schemas import PluginBody, TestBody
from ..serializers import plugin_entry

router = APIRouter(prefix="/api")


@router.get("/plugins")
def api_plugins(ctx: WebContext = Depends(get_ctx)):
    config = ctx.cfg()
    categories = [
        {
            "category": cat,
            # 跳过 hidden 插件（如 null 兜底刮削器），它们仅供内部使用
            "entries": [
                plugin_entry(config, cat, n)
                for n in available(cat)
                if not get_plugin(cat, n).hidden
            ],
        }
        for cat in CATEGORIES
    ]
    return {"categories": categories}


@router.put("/plugins/{category}/{name}")
def api_plugin_update(category: str, name: str, body: PluginBody,
                      ctx: WebContext = Depends(get_ctx)):
    if category not in CATEGORIES:
        raise HTTPException(404, f"未知类别: {category}")
    try:
        cls = get_plugin(category, name)
    except KeyError:
        raise HTTPException(404, f"未知插件: {category}/{name}")
    try:
        cls.ConfigModel.model_validate(body.config)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    # 刮削器固定为 TMDB，不可关闭——强制启用，无视请求里的 enabled
    enabled = True if category == "scraper" else body.enabled
    # 持久化(保留注释) + 热重载
    cfgio.upsert_plugin(ctx.config_path, category, name, enabled, body.config)
    config = ctx.manager.reload()
    return plugin_entry(config, category, name)


@router.post("/plugins/{category}/{name}/test")
async def api_plugin_test(category: str, name: str, body: TestBody,
                          ctx: WebContext = Depends(get_ctx)):
    if category not in CATEGORIES:
        raise HTTPException(404, f"未知类别: {category}")
    try:
        cls = get_plugin(category, name)
    except KeyError:
        raise HTTPException(404, f"未知插件: {category}/{name}")
    try:
        inst = cls(cls.ConfigModel.model_validate(body.config))
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    try:
        ok, msg = await run_in_threadpool(inst.test)
    except Exception as e:  # noqa: BLE001
        ok, msg = False, f"测试异常: {e}"
    finally:
        await run_in_threadpool(inst.close)
    return {"ok": ok, "message": msg}


@router.get("/subscribers")
def api_subscribers(ctx: WebContext = Depends(get_ctx)):
    out = []
    for name in available("subscriber"):
        cls = get_plugin("subscriber", name)
        out.append({"name": name, "schema": cls.ConfigModel.model_json_schema()})
    return {"subscribers": out}
