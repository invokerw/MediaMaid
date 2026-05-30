"""FastAPI 应用：JSON API + 托管 React SPA 静态产物。

API 在 /api/* 下；其余路径返回构建好的 index.html，交给前端路由。
复用 store/pipeline/plugins/subscribe 现有能力，不重写逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..config import load_config
from ..logging_conf import get_logger
from ..pipeline import Pipeline
from ..plugins import CATEGORIES, available, load_plugins
from ..store import Record, StateStore
from ..subscribe import SubscribeRunner

log = get_logger(__name__)

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_INDEX = _STATIC / "index.html"

_NOT_BUILT = (
    "<h1>MediaMaid</h1><p>前端尚未构建。请执行："
    "<pre>cd mediamaid/web/frontend && npm install && npm run build</pre></p>"
)


def _record_dict(r: Record) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "action": r.action,
        "src_path": r.src_path,
        "src_name": Path(r.src_path).name,
        "dst_path": r.dst_path,
        "dst_name": Path(r.dst_path).name if r.dst_path else None,
        "ts": r.ts,
    }


class ScanBody(BaseModel):
    dry_run: bool = False


def create_app(config_path: Path) -> FastAPI:
    config_path = Path(config_path)
    load_plugins()
    config = load_config(config_path)
    store = StateStore(config.state_db)

    app = FastAPI(title="MediaMaid")

    # ---- JSON API ----
    @app.get("/api/dashboard")
    def api_dashboard():
        return {
            "counts": store.counts(),
            "records": [_record_dict(r) for r in store.recent(10)],
        }

    @app.get("/api/records")
    def api_records(status: Optional[str] = None):
        rows = store.recent(500)
        if status:
            rows = [r for r in rows if r.status == status]
        return {"records": [_record_dict(r) for r in rows]}

    @app.get("/api/plugins")
    def api_plugins():
        categories = []
        for cat in CATEGORIES:
            enabled = {s.name for s in config.plugin_specs(cat)}
            categories.append(
                {
                    "category": cat,
                    "entries": [
                        {"name": n, "enabled": n in enabled} for n in available(cat)
                    ],
                }
            )
        return {"categories": categories}

    @app.get("/api/config")
    def api_config():
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as e:
            text = f"# 无法读取配置文件: {e}"
        return {"path": str(config_path), "text": text}

    @app.post("/api/scan")
    async def api_scan(body: ScanBody):
        pipeline = Pipeline(config, store)
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

    @app.post("/api/subscribe")
    async def api_subscribe():
        runner = SubscribeRunner(config, store, notify=Pipeline(config, store).notify)
        submitted = await run_in_threadpool(runner.run_once)
        return {"submitted": submitted}

    # ---- 托管 React SPA ----
    assets = _STATIC / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def spa(full_path: str):
        # API 之外的路径都交给前端路由
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if _INDEX.is_file():
            return FileResponse(str(_INDEX))
        return HTMLResponse(_NOT_BUILT, status_code=503)

    return app
