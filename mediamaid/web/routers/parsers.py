"""TMDB 规则（绑定 + 忽略）CRUD。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ...config import TmdbRule
from .. import cfgio
from ..deps import WebContext, get_ctx
from ..schemas import TmdbRuleBody, TmdbRuleUpdate
from ..serializers import tmdb_rule_dict

router = APIRouter(prefix="/api")


def _find_rule(ctx: WebContext, rid: str):
    r = next((x for x in ctx.cfg().tmdb_rules if x.id == rid), None)
    if r is None:
        raise HTTPException(404, f"规则不存在: {rid}")
    return r


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
