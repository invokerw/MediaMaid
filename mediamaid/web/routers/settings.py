"""配置文件只读查看与顶层设置编辑。"""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ...config import Config
from .. import cfgio
from ..deps import WebContext, get_ctx
from ..schemas import SettingsBody
from ..serializers import settings_dict

router = APIRouter(prefix="/api")


@router.get("/config")
def api_config(ctx: WebContext = Depends(get_ctx)):
    try:
        text = ctx.config_path.read_text(encoding="utf-8")
    except OSError as e:
        text = f"# 无法读取配置文件: {e}"
    return {"path": str(ctx.config_path), "text": text}


@router.get("/settings")
def api_settings_get(ctx: WebContext = Depends(get_ctx)):
    return settings_dict(ctx.cfg())


@router.put("/settings")
def api_settings_put(body: SettingsBody, ctx: WebContext = Depends(get_ctx)):
    values = body.model_dump(exclude_none=True)
    # 校验：把当前 yaml 与提交值合并后整体校验
    try:
        with ctx.config_path.open("r", encoding="utf-8") as f:
            merged = yaml.safe_load(f) or {}
    except OSError:
        merged = {}
    for k, v in values.items():
        if k in ("filters", "naming") and isinstance(v, dict):
            merged.setdefault(k, {}).update(v)
        else:
            merged[k] = v
    try:
        Config.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    cfgio.update_settings(ctx.config_path, values)
    return settings_dict(ctx.manager.reload())
