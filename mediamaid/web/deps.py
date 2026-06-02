"""Web 共享上下文与依赖：配置管理、状态库、受管路径安全校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException, Request

from ..config import Config, ConfigManager
from ..logging_conf import get_logger
from ..plugins import create
from ..plugins.base import Downloader
from ..store import StateStore

log = get_logger(__name__)


@dataclass
class WebContext:
    """一个 Web 应用实例共享的运行期依赖。挂在 app.state.ctx 上。"""

    config_path: Path
    manager: ConfigManager
    store: StateStore
    # 下载器实例缓存：下载管理页每数秒轮询一次，不能每次都重连（qB 还要重新登录）。
    # 按当前 Config 对象身份缓存，配置热重载（get() 返回新对象）时整体重建。
    _dl_cache: Dict[str, Downloader] = field(default_factory=dict, init=False)
    _dl_cfg_id: int = field(default=0, init=False)

    def cfg(self) -> Config:
        """当前配置（ConfigManager 按文件 mtime 自动热重载）。"""
        return self.manager.get()

    def downloaders(self) -> List[Downloader]:
        """已配置且启用的下载器实例（带缓存；配置变更时重建并关闭旧实例）。"""
        config = self.cfg()
        if id(config) != self._dl_cfg_id:
            for d in self._dl_cache.values():
                try:
                    d.close()
                except Exception:  # noqa: BLE001 - 关闭尽力而为
                    pass
            cache: Dict[str, Downloader] = {}
            for spec in config.plugin_specs("downloader"):
                try:
                    cache[spec.name] = create("downloader", spec.name, spec.config)
                except Exception as e:  # noqa: BLE001
                    log.error("加载下载器 %s 失败: %s", spec.name, e)
            self._dl_cache = cache
            self._dl_cfg_id = id(config)
        return list(self._dl_cache.values())

    def downloader(self, name: str) -> Downloader:
        """按名取单个下载器实例；不存在抛 404。"""
        self.downloaders()  # 确保缓存为最新
        d = self._dl_cache.get(name)
        if d is None:
            raise HTTPException(404, f"下载器未配置或未启用: {name}")
        return d


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
