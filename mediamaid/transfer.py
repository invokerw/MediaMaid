"""原子传输原语：硬链接 / 复制 / 移动，含跨设备回退与冲突处理。"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

from .logging_conf import get_logger
from .models import TransferAction

log = get_logger(__name__)


class ConflictError(Exception):
    pass


def _resolve_conflict(dest: Path, on_conflict: str) -> Path | None:
    """处理目标已存在。返回最终目标路径，或 None 表示应跳过。"""
    if not dest.exists():
        return dest
    if on_conflict == "skip":
        log.info("目标已存在，跳过: %s", dest)
        return None
    if on_conflict == "overwrite":
        return dest
    if on_conflict == "rename":
        stem, suffix = dest.stem, dest.suffix
        i = 1
        while True:
            candidate = dest.with_name(f"{stem} ({i}){suffix}")
            if not candidate.exists():
                return candidate
            i += 1
    raise ValueError(f"未知的 on_conflict 策略: {on_conflict}")


def _same_filesystem(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.stat().st_dev
    except OSError:
        return False


def transfer(
    source: Path,
    dest: Path,
    action: TransferAction,
    on_conflict: str = "skip",
    dry_run: bool = False,
) -> Path | None:
    """把 source 落地到 dest。返回实际写入路径，跳过则返回 None。"""
    source = Path(source)
    dest = Path(dest)

    final = _resolve_conflict(dest, on_conflict)
    if final is None:
        return None

    if dry_run:
        log.info("[dry-run] %s: %s -> %s", action.value, source, final)
        return final

    final.parent.mkdir(parents=True, exist_ok=True)
    # overwrite 时先删旧目标
    if final.exists() and on_conflict == "overwrite":
        final.unlink()

    if action == TransferAction.HARDLINK:
        _do_hardlink(source, final)
    elif action == TransferAction.COPY:
        _do_copy(source, final)
    elif action == TransferAction.MOVE:
        _do_move(source, final)
    elif action == TransferAction.SYMLINK:
        _do_symlink(source, final)
    else:
        raise ValueError(f"未知动作: {action}")

    log.info("%s: %s -> %s", action.value, source.name, final)
    return final


def _do_hardlink(source: Path, dest: Path) -> None:
    """硬链接；跨设备(EXDEV)自动回退到复制。"""
    try:
        os.link(source, dest)
    except OSError as e:
        if e.errno == errno.EXDEV:
            log.warning("跨设备无法硬链接，回退复制: %s", source.name)
            _do_copy(source, dest)
        else:
            raise


def _do_copy(source: Path, dest: Path) -> None:
    """复制到临时文件后原子改名，避免半成品。"""
    tmp = dest.with_name(dest.name + ".mmpart")
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _do_symlink(source: Path, dest: Path) -> None:
    """创建指向源文件的软链接（用绝对路径，跨设备无 EXDEV 限制）。"""
    os.symlink(source.resolve(), dest)


def _do_move(source: Path, dest: Path) -> None:
    if _same_filesystem(source, dest.parent):
        os.replace(source, dest)
    else:
        # 跨设备：先复制再删源
        _do_copy(source, dest)
        source.unlink()
