"""插件注册表与发现机制。

发现来源：
1. 本地目录扫描：导入 mediamaid/plugins/<category>/ 下所有模块（触发 @register）。
2. entry_points：组 "mediamaid.plugins" 下的外部包。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Type

from ..logging_conf import get_logger
from .base import CATEGORIES, Plugin

log = get_logger(__name__)

# category -> {name -> 插件类}
_REGISTRY: Dict[str, Dict[str, Type[Plugin]]] = {cat: {} for cat in CATEGORIES}
_loaded = False


def register(cls: Type[Plugin]) -> Type[Plugin]:
    """注册插件类的装饰器。"""
    if not cls.category or cls.category not in CATEGORIES:
        raise ValueError(f"插件 {cls.__name__} 的 category 非法: {cls.category!r}")
    if not cls.name:
        raise ValueError(f"插件 {cls.__name__} 缺少 name")
    base = CATEGORIES[cls.category]
    if not issubclass(cls, base):
        raise TypeError(f"{cls.__name__} 必须继承 {base.__name__}")
    existing = _REGISTRY[cls.category].get(cls.name)
    if existing and existing is not cls:
        log.warning("插件覆盖: %s:%s (%s 覆盖 %s)", cls.category, cls.name,
                    cls.__name__, existing.__name__)
    _REGISTRY[cls.category][cls.name] = cls
    return cls


def available(category: str) -> List[str]:
    """列出某类别已注册的插件名。"""
    return sorted(_REGISTRY.get(category, {}).keys())


def get(category: str, name: str) -> Type[Plugin]:
    try:
        return _REGISTRY[category][name]
    except KeyError:
        raise KeyError(
            f"未找到插件 {category}:{name}；可用: {available(category)}"
        ) from None


def create(category: str, name: str, config: dict | None = None) -> Plugin:
    """按配置创建插件实例（配置经 ConfigModel 校验）。"""
    cls = get(category, name)
    cfg = cls.ConfigModel.model_validate(config or {})
    return cls(cfg)


def close_plugins(plugins) -> None:
    """逐个关闭插件实例，单个失败不影响其他（热重载替换前调用）。"""
    for p in plugins or []:
        try:
            p.close()
        except Exception as e:  # noqa: BLE001
            log.warning("关闭插件 %s 失败: %s", getattr(p, "name", p), e)


def load_plugins() -> None:
    """发现并注册所有插件（幂等）。"""
    global _loaded
    if _loaded:
        return
    _load_builtin()
    _load_entry_points()
    _loaded = True
    for cat in CATEGORIES:
        log.debug("插件[%s]: %s", cat, available(cat))


def _load_builtin() -> None:
    """导入 mediamaid/plugins/<category>/ 下所有子模块。"""
    import mediamaid.plugins as pkg

    for cat in CATEGORIES:
        try:
            sub = importlib.import_module(f"{pkg.__name__}.{cat}")
        except ModuleNotFoundError:
            continue
        for mod in pkgutil.iter_modules(sub.__path__):
            if mod.name.startswith("_"):
                continue
            try:
                importlib.import_module(f"{sub.__name__}.{mod.name}")
            except Exception as e:  # noqa: BLE001 - 单个插件加载失败不影响其他
                log.warning("加载插件模块失败 %s.%s: %s", cat, mod.name, e)


def _load_entry_points() -> None:
    """加载 entry_points 组 'mediamaid.plugins' 下的外部插件。"""
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return
    try:
        eps = entry_points(group="mediamaid.plugins")
    except TypeError:  # py<3.10 兼容
        eps = entry_points().get("mediamaid.plugins", [])
    for ep in eps:
        try:
            ep.load()  # 模块顶层应有 @register
        except Exception as e:  # noqa: BLE001
            log.warning("加载外部插件失败 %s: %s", ep.name, e)
