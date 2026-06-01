"""FastAPI 应用装配：建上下文 → 挂载各 API router → 托管 React SPA 静态产物。

API 在 /api/* 下（见 routers/）；其余路径返回构建好的 index.html，交给前端路由。
具体端点实现按领域拆分到 routers/ 子模块，本文件只负责组装。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import ConfigManager
from ..logging_conf import get_logger
from ..plugins import load_plugins
from ..store import StateStore
from .deps import WebContext
from .routers import dashboard, files, plugins, parsers, settings, subscriptions

log = get_logger(__name__)

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_INDEX = _STATIC / "index.html"

_NOT_BUILT = (
    "<h1>MediaMaid</h1><p>前端尚未构建。请执行："
    "<pre>cd mediamaid/web/frontend && npm install && npm run build</pre></p>"
)

_ROUTERS = (dashboard, plugins, parsers, files, settings, subscriptions)


def create_app(config_path: Path) -> FastAPI:
    config_path = Path(config_path)
    load_plugins()
    # ConfigManager：按文件 mtime 自动热重载，处理器一律读 ctx.cfg()
    manager = ConfigManager(config_path)
    store = StateStore(manager.get().state_db)

    app = FastAPI(title="MediaMaid")
    app.state.ctx = WebContext(config_path=config_path, manager=manager, store=store)

    for module in _ROUTERS:
        app.include_router(module.router)

    # ---- 托管 React SPA（catch-all 必须最后注册，避免吞掉 /api 与 /assets）----
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
