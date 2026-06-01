"""解析器链（按序尝试）CRUD 与解析测试。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ...identify import Identifier
from ...plugins import available, get as get_plugin
from .. import cfgio
from ..deps import WebContext, get_ctx, safe_path
from ..schemas import DeleteBody, ParserBody, ParserUpdate, ParseTestBody
from ..serializers import parser_dict

router = APIRouter(prefix="/api")


def _find_parser(ctx: WebContext, pid: str):
    p = next((x for x in ctx.cfg().parsers if x.id == pid), None)
    if p is None:
        raise HTTPException(404, f"解析器不存在: {pid}")
    return p


def _parse_one(ident: Identifier, name: str) -> dict:
    res, matched = ident.parse_name(name)
    if res is None:
        return {"name": name, "matched": None}
    return {
        "name": name,
        "matched": matched,
        "type": res.type.value,
        "title": res.title,
        "year": res.year,
        "season": res.season,
        "episode": res.episode,
    }


@router.get("/parsers/types")
def api_parser_types():
    out = []
    for name in available("parser"):
        cls = get_plugin("parser", name)
        out.append({"name": name, "schema": cls.ConfigModel.model_json_schema()})
    return {"parsers": out}


@router.get("/parsers")
def api_parsers(ctx: WebContext = Depends(get_ctx)):
    return {"parsers": [parser_dict(p) for p in ctx.cfg().parsers]}


@router.post("/parsers")
def api_parser_create(body: ParserBody, ctx: WebContext = Depends(get_ctx)):
    try:
        cls = get_plugin("parser", body.parser)
    except KeyError:
        raise HTTPException(404, f"未知解析器: {body.parser}")
    try:
        cls.ConfigModel.model_validate(body.config)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    pid = uuid.uuid4().hex[:8]
    cfgio.add_list_item(ctx.config_path, "parsers", {
        "id": pid, "name": body.name, "parser": body.parser,
        "enabled": body.enabled, "config": body.config,
    })
    ctx.manager.reload()
    return parser_dict(_find_parser(ctx, pid))


@router.put("/parsers/{pid}")
def api_parser_update(pid: str, body: ParserUpdate, ctx: WebContext = Depends(get_ctx)):
    p = _find_parser(ctx, pid)
    parser = body.parser or p.parser
    config = body.config if body.config is not None else p.config
    try:
        cls = get_plugin("parser", parser)
        cls.ConfigModel.model_validate(config)
    except KeyError:
        raise HTTPException(404, f"未知解析器: {parser}")
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    cfgio.update_list_item(ctx.config_path, "parsers", pid, body.model_dump(exclude_none=True))
    ctx.manager.reload()
    return parser_dict(_find_parser(ctx, pid))


@router.delete("/parsers/{pid}")
def api_parser_delete(pid: str, ctx: WebContext = Depends(get_ctx)):
    _find_parser(ctx, pid)
    cfgio.delete_list_item(ctx.config_path, "parsers", pid)
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
