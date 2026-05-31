"""FastAPI 应用：JSON API + 托管 React SPA 静态产物。

API 在 /api/* 下；其余路径返回构建好的 index.html，交给前端路由。
复用 store/pipeline/plugins/subscribe 现有能力，不重写逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from . import cfgio
from ..config import Config, ConfigManager
from ..logging_conf import get_logger
from ..models import Release
from ..pipeline import Pipeline
from ..plugins import CATEGORIES, available, get as get_plugin, load_plugins
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


class PluginBody(BaseModel):
    enabled: bool = True
    config: dict = {}


class TestBody(BaseModel):
    config: dict = {}


class ReleaseBody(BaseModel):
    title: str
    guid: str
    magnet: Optional[str] = None
    torrent_url: Optional[str] = None
    link: Optional[str] = None


class FiltersBody(BaseModel):
    video_extensions: Optional[List[str]] = None
    min_size_mb: Optional[int] = None
    exclude_keywords: Optional[List[str]] = None


class NamingBody(BaseModel):
    movie: Optional[str] = None
    episode: Optional[str] = None
    movie_no_year: Optional[str] = None
    episode_no_year: Optional[str] = None


class SettingsBody(BaseModel):
    """顶层可编辑设置，全部可选；仅提交的字段会被更新。"""

    source_dirs: Optional[List[str]] = None
    library_dir: Optional[str] = None
    action: Optional[str] = None
    on_conflict: Optional[str] = None
    stable_seconds: Optional[int] = None
    rescan_interval: Optional[int] = None
    subscribe_interval: Optional[int] = None
    poll_completed: Optional[bool] = None
    poll_interval: Optional[int] = None
    write_nfo: Optional[bool] = None
    download_artwork: Optional[bool] = None
    filters: Optional[FiltersBody] = None
    naming: Optional[NamingBody] = None


def _settings_dict(config: Config) -> dict:
    """把当前配置序列化为前端可编辑的设置视图。"""
    return {
        "source_dirs": [str(p) for p in config.source_dirs],
        "library_dir": str(config.library_dir),
        "action": config.action.value,
        "on_conflict": config.on_conflict,
        "stable_seconds": config.stable_seconds,
        "rescan_interval": config.rescan_interval,
        "subscribe_interval": config.subscribe_interval,
        "poll_completed": config.poll_completed,
        "poll_interval": config.poll_interval,
        "write_nfo": config.write_nfo,
        "download_artwork": config.download_artwork,
        "filters": {
            "video_extensions": config.filters.video_extensions,
            "min_size_mb": config.filters.min_size_mb,
            "exclude_keywords": config.filters.exclude_keywords,
        },
        "naming": {
            "movie": config.naming.movie,
            "episode": config.naming.episode,
            "movie_no_year": config.naming.movie_no_year,
            "episode_no_year": config.naming.episode_no_year,
        },
    }


def _plugin_entry(config, category: str, name: str) -> dict:
    """组装单个插件的 UI 信息：启停 + 当前配置 + 配置 schema。"""
    spec = next((s for s in config.plugins.get(category, []) if s.name == name), None)
    cls = get_plugin(category, name)
    return {
        "name": name,
        "enabled": bool(spec.enabled) if spec else False,
        "configured": spec is not None,
        "config": dict(spec.config) if spec else {},
        "schema": cls.ConfigModel.model_json_schema(),
    }


def create_app(config_path: Path) -> FastAPI:
    config_path = Path(config_path)
    load_plugins()
    # ConfigManager：按文件 mtime 自动热重载，处理器一律读 cfg()
    manager = ConfigManager(config_path)

    def cfg():
        return manager.get()

    store = StateStore(cfg().state_db)

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
        config = cfg()
        categories = [
            {
                "category": cat,
                "entries": [_plugin_entry(config, cat, n) for n in available(cat)],
            }
            for cat in CATEGORIES
        ]
        return {"categories": categories}

    @app.put("/api/plugins/{category}/{name}")
    def api_plugin_update(category: str, name: str, body: PluginBody):
        if category not in CATEGORIES:
            raise HTTPException(404, f"未知类别: {category}")
        try:
            cls = get_plugin(category, name)
        except KeyError:
            raise HTTPException(404, f"未知插件: {category}/{name}")
        # 校验配置
        try:
            cls.ConfigModel.model_validate(body.config)
        except ValidationError as e:
            raise HTTPException(422, e.errors())
        # 持久化(保留注释) + 热重载
        cfgio.upsert_plugin(config_path, category, name, body.enabled, body.config)
        config = manager.reload()
        return _plugin_entry(config, category, name)

    @app.post("/api/plugins/{category}/{name}/test")
    async def api_plugin_test(category: str, name: str, body: TestBody):
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
        return {"ok": ok, "message": msg}

    @app.get("/api/config")
    def api_config():
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as e:
            text = f"# 无法读取配置文件: {e}"
        return {"path": str(config_path), "text": text}

    @app.get("/api/settings")
    def api_settings_get():
        return _settings_dict(cfg())

    @app.put("/api/settings")
    def api_settings_put(body: SettingsBody):
        values = body.model_dump(exclude_none=True)
        # 校验：把当前 yaml 与提交值合并后整体校验
        try:
            with config_path.open("r", encoding="utf-8") as f:
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
        cfgio.update_settings(config_path, values)
        return _settings_dict(manager.reload())

    @app.post("/api/scan")
    async def api_scan(body: ScanBody):
        pipeline = Pipeline(cfg(), store)
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
        config = cfg()
        runner = SubscribeRunner(config, store, notify=Pipeline(config, store).notify)
        submitted = await run_in_threadpool(runner.run_once)
        return {"submitted": submitted}

    def _release_dict(rel) -> dict:
        return {
            "title": rel.title,
            "guid": rel.guid,
            "magnet": rel.magnet,
            "torrent_url": rel.torrent_url,
            "link": rel.link,
            "size": rel.size,
            "pub_date": rel.pub_date,
            "source": rel.source,
            "seen": store.release_seen(rel.guid),
        }

    @app.get("/api/subscriptions/preview")
    async def api_sub_preview():
        config = cfg()
        runner = SubscribeRunner(config, store)
        releases = await run_in_threadpool(runner.preview)
        return {
            "subscribers": [s.name for s in runner.subscribers],
            "releases": [_release_dict(r) for r in releases],
        }

    @app.get("/api/releases")
    def api_releases(limit: int = 200):
        return {
            "releases": [
                {"guid": g, "title": t, "ts": ts}
                for (g, t, ts) in store.recent_releases(limit)
            ]
        }

    @app.post("/api/releases/download")
    async def api_release_download(rel: ReleaseBody):
        config = cfg()
        runner = SubscribeRunner(config, store, notify=Pipeline(config, store).notify)
        if not runner.downloaders:
            raise HTTPException(400, "未配置下载器")
        release = Release(
            title=rel.title,
            guid=rel.guid,
            magnet=rel.magnet,
            torrent_url=rel.torrent_url,
            link=rel.link,
        )
        ok = await run_in_threadpool(runner.download_release, release)
        if not ok:
            raise HTTPException(502, "下载器未接受该资源")
        return {"ok": True}

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
