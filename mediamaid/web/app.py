"""FastAPI 应用工厂与路由。

仪表盘 + 动作（手动扫描/订阅、dry-run 预览）；配置/插件只读。
复用 store/pipeline/plugins/subscribe 现有能力，不重写逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ..config import load_config
from ..logging_conf import get_logger
from ..pipeline import Pipeline
from ..plugins import CATEGORIES, available, load_plugins
from ..store import StateStore
from ..subscribe import SubscribeRunner

log = get_logger(__name__)

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def create_app(config_path: Path) -> FastAPI:
    config_path = Path(config_path)
    load_plugins()
    config = load_config(config_path)
    store = StateStore(config.state_db)

    app = FastAPI(title="MediaMaid")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    app.state.config = config
    app.state.config_path = config_path
    app.state.store = store

    def render(request: Request, name: str, active: str, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"active": active, **ctx})

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        return render(
            request, "dashboard.html", "dashboard",
            counts=store.counts(), records=store.recent(10),
        )

    @app.get("/records", response_class=HTMLResponse)
    def records(request: Request, status: Optional[str] = None):
        rows = store.recent(500)
        if status:
            rows = [r for r in rows if r.status == status]
        return render(request, "records.html", "records", records=rows, status=status or "")

    @app.get("/plugins", response_class=HTMLResponse)
    def plugins(request: Request):
        data = []
        for cat in CATEGORIES:
            enabled = {s.name for s in config.plugin_specs(cat)}
            data.append(
                {
                    "category": cat,
                    "entries": [
                        {"name": n, "enabled": n in enabled} for n in available(cat)
                    ],
                }
            )
        return render(request, "plugins.html", "plugins", categories=data)

    @app.get("/config", response_class=HTMLResponse)
    def config_view(request: Request):
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as e:
            text = f"# 无法读取配置文件: {e}"
        return render(
            request, "config.html", "config",
            config_text=text, config_path=str(config_path),
        )

    @app.post("/api/scan")
    async def api_scan(dry_run: bool = Form(False)):
        pipeline = Pipeline(config, store)
        results = await run_in_threadpool(pipeline.scan, dry_run)
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
        return JSONResponse({"dry_run": dry_run, "summary": summary, "items": items})

    @app.post("/api/subscribe")
    async def api_subscribe():
        runner = SubscribeRunner(config, store, notify=Pipeline(config, store).notify)
        submitted = await run_in_threadpool(runner.run_once)
        return JSONResponse({"submitted": submitted})

    return app
