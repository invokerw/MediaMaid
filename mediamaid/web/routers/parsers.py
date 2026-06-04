"""TMDB 规则（绑定 + 忽略）CRUD 与解析测试。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ...config import TmdbRule
from ...identify import Identifier
from .. import cfgio
from ..deps import WebContext, get_ctx, safe_path
from ..schemas import DeleteBody, ParseTestBody, TmdbRuleBody, TmdbRuleUpdate
from ..serializers import tmdb_rule_dict

router = APIRouter(prefix="/api")


def _find_rule(ctx: WebContext, rid: str):
    r = next((x for x in ctx.cfg().tmdb_rules if x.id == rid), None)
    if r is None:
        raise HTTPException(404, f"规则不存在: {rid}")
    return r


def _parse_one(ident: Identifier, name: str) -> dict:
    res, matched = ident.parse_name(name)
    if res is None:
        return {"name": name, "matched": None}
    return {
        "name": name,
        "matched": matched,
        "type": res.type.value,
        "title": res.title,
        "tmdb_id": res.tmdb_id,
        "year": res.year,
        "season": res.season,
        "episode": res.episode,
    }


@router.get("/tmdb-rules")
def api_rules(ctx: WebContext = Depends(get_ctx)):
    return {"rules": [tmdb_rule_dict(r) for r in ctx.cfg().tmdb_rules]}


@router.post("/tmdb-rules")
def api_rule_create(body: TmdbRuleBody, ctx: WebContext = Depends(get_ctx)):
    rid = uuid.uuid4().hex[:8]
    item = {"id": rid, **body.model_dump()}
    try:
        TmdbRule.model_validate(item)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    cfgio.add_list_item(ctx.config_path, "tmdb_rules", item)
    ctx.manager.reload()
    return tmdb_rule_dict(_find_rule(ctx, rid))


@router.put("/tmdb-rules/{rid}")
def api_rule_update(rid: str, body: TmdbRuleUpdate, ctx: WebContext = Depends(get_ctx)):
    r = _find_rule(ctx, rid)
    fields = body.model_dump(exclude_none=True)
    merged = {**tmdb_rule_dict(r), **fields}
    try:
        TmdbRule.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    cfgio.update_list_item(ctx.config_path, "tmdb_rules", rid, fields)
    ctx.manager.reload()
    return tmdb_rule_dict(_find_rule(ctx, rid))


@router.delete("/tmdb-rules/{rid}")
def api_rule_delete(rid: str, ctx: WebContext = Depends(get_ctx)):
    _find_rule(ctx, rid)
    cfgio.delete_list_item(ctx.config_path, "tmdb_rules", rid)
    ctx.manager.reload()
    return {"ok": True}


@router.post("/parse/test")
def api_parse_test(body: ParseTestBody, ctx: WebContext = Depends(get_ctx)):
    # 对单个文件名测试解析（解析的是文件名，不是种子标题）
    return _parse_one(Identifier(ctx.cfg()), body.name)


@router.post("/parse/test-dir")
def api_parse_test_dir(body: DeleteBody, limit: int = 300, ctx: WebContext = Depends(get_ctx)):
    """对某目录下真实下载的文件逐个测试解析（合集文件夹会递归到每个文件）。"""
    base = safe_path(ctx, body.path)
    if not base.is_dir():
        raise HTTPException(400, "不是目录")
    ident = Identifier(ctx.cfg())
    results = []
    for p in sorted(base.rglob("*")):
        if not ident.accept_file(p):
            continue
        results.append({**_parse_one(ident, p.name), "path": str(p)})
        if len(results) >= limit:
            break
    return {"results": results}
