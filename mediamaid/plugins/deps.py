"""可选依赖的惰性加载 + 缺失时自动安装。

插件用到的重依赖（qbittorrent-api / transmission-rpc / feedparser 等）是 pyproject
的可选依赖组，未必装在运行环境里。本模块在首次用到时尝试 import，缺失则自动
`pip install` 后重试，把「缺依赖」与「连接/配置错误」彻底分开——插件不再把两类
问题收敛成同一句笼统提示。

自动安装默认开启；离线/受控环境可设 `MEDIAMAID_AUTO_INSTALL=0`（或 false/no）关闭，
此时缺依赖直接返回明确的手动安装提示。
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
from types import ModuleType
from typing import Optional, Set, Tuple

from ..logging_conf import get_logger

log = get_logger(__name__)

# 串行化安装，避免多线程（scan_workers / Web 并发测试）同时装同一个包
_install_lock = threading.Lock()
# 已尝试安装但失败的 pip 包：避免每次调用都重复联网安装
_failed: Set[str] = set()


def _auto_install_enabled() -> bool:
    return os.environ.get("MEDIAMAID_AUTO_INSTALL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def require(
    module: str, pip_name: Optional[str] = None
) -> Tuple[Optional[ModuleType], Optional[str]]:
    """导入可选依赖 ``module``；缺失则尝试自动安装 ``pip_name`` 后重试。

    参数:
        module: 要 import 的模块名（如 ``qbittorrentapi``）。
        pip_name: 对应的 pip 包名（如 ``qbittorrent-api``）；默认与 module 同名。

    返回 ``(模块, 错误信息)``：成功时错误信息为 None；失败时模块为 None 且错误信息
    描述具体原因（缺依赖 / 安装失败 / 装了仍无法导入），供调用方原样展示给用户。
    """
    pip_name = pip_name or module
    try:
        return importlib.import_module(module), None
    except ImportError:
        pass

    if not _auto_install_enabled():
        return None, f"缺少依赖 {pip_name}（已禁用自动安装），请手动执行 pip install {pip_name}"

    with _install_lock:
        # 拿到锁后再试一次：可能已被其它线程在等待期间装好
        try:
            return importlib.import_module(module), None
        except ImportError:
            pass
        if pip_name in _failed:
            return None, f"依赖 {pip_name} 此前安装失败（已跳过重试），请手动 pip install {pip_name}"

        log.info("缺少依赖 %s，正在自动安装…", pip_name)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pip_name],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except Exception as e:  # noqa: BLE001 - 安装失败原因多样，统一兜底
            _failed.add(pip_name)
            detail = (getattr(e, "stderr", "") or str(e)).strip()
            log.error("自动安装 %s 失败: %s", pip_name, detail)
            return None, f"依赖 {pip_name} 自动安装失败: {detail[:300]}"

        importlib.invalidate_caches()
        try:
            mod = importlib.import_module(module)
        except ImportError as e:
            _failed.add(pip_name)
            return None, f"已安装 {pip_name} 但仍无法导入 {module}: {e}"
        log.info("依赖 %s 安装成功", pip_name)
        return mod, None
