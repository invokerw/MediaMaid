"""Web 共享上下文与依赖：配置管理、状态库、受管路径安全校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from fastapi import HTTPException, Request

from ..config import Config, ConfigManager
from ..store import StateStore


@dataclass
class WebContext:
    """一个 Web 应用实例共享的运行期依赖。挂在 app.state.ctx 上。"""

    config_path: Path
    manager: ConfigManager
    store: StateStore

    def cfg(self) -> Config:
        """当前配置（ConfigManager 按文件 mtime 自动热重载）。"""
        return self.manager.get()


def get_ctx(request: Request) -> WebContext:
    """FastAPI 依赖：取出本应用的 WebContext。"""
    return request.app.state.ctx


# ---- 受管路径安全（仅允许操作源目录 / 媒体库范围内）----
def managed_roots(ctx: WebContext) -> List[Path]:
    config = ctx.cfg()
    out: List[Path] = []
    for r in list(config.source_dirs) + [config.library_dir]:
        try:
            out.append(Path(r).resolve())
        except OSError:
            continue
    return out


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_path(ctx: WebContext, path_str: str, *, allow_root: bool = True) -> Path:
    """解析路径并确保位于某个受管根内；allow_root=False 时禁止恰好是根。"""
    p = Path(path_str).resolve()
    roots = managed_roots(ctx)
    inside = any(p == r or _is_within(p, r) for r in roots)
    if not inside:
        raise HTTPException(403, "路径超出受管目录（源目录/媒体库）范围")
    if not allow_root and any(p == r for r in roots):
        raise HTTPException(403, "不允许操作受管根目录本身")
    return p
