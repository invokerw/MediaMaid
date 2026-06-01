"""文件管理（受管根内浏览/重命名/删除）、目录选择器、硬链接自检。"""

from __future__ import annotations

import errno
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import WebContext, get_ctx, safe_path
from ..schemas import DeleteBody, RenameBody

router = APIRouter(prefix="/api")


@router.get("/fs")
def api_fs(path: Optional[str] = None):
    """列出某目录下的子目录，供前端目录选择器使用（不限受管根）。"""
    base = Path(path).expanduser() if path else Path.home()
    result = {"path": str(base), "parent": str(base.parent), "dirs": [], "error": None}
    try:
        if not base.is_dir():
            result["error"] = "不是目录或不存在"
            return result
        dirs = []
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    dirs.append({"name": child.name, "path": str(child)})
            except OSError:
                continue
        result["dirs"] = dirs
    except PermissionError:
        result["error"] = "无权限访问该目录"
    except OSError as e:
        result["error"] = str(e)
    return result


@router.get("/diag/hardlink")
def api_diag_hardlink(ctx: WebContext = Depends(get_ctx)):
    """逐源目录实测能否硬链到媒体库（同一文件系统才行，否则回退复制）。"""
    config = ctx.cfg()
    lib = Path(config.library_dir)
    lib_ok, lib_err = True, ""
    try:
        lib.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        lib_ok, lib_err = False, str(e)

    results = []
    for src in config.source_dirs:
        src = Path(src)
        entry = {"source": str(src), "library": str(lib), "ok": False, "detail": ""}
        if not src.is_dir():
            entry["detail"] = "源目录不存在"
        elif not lib_ok:
            entry["detail"] = f"媒体库不可写: {lib_err}"
        else:
            s = src / f".mm_hltest_{uuid.uuid4().hex[:8]}"
            d = lib / f".mm_hltest_{uuid.uuid4().hex[:8]}"
            try:
                s.write_bytes(b"x")
                os.link(s, d)
                entry["ok"] = True
                entry["detail"] = "同一文件系统，硬链接可用 ✓"
            except OSError as e:
                if e.errno == errno.EXDEV:
                    entry["detail"] = "跨设备/不同挂载，硬链接不可用，将回退为复制"
                else:
                    entry["detail"] = f"硬链接失败: {e}"
            finally:
                for p in (d, s):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        results.append(entry)
    return {"action": config.action.value, "results": results}


@router.get("/files/roots")
def api_files_roots(ctx: WebContext = Depends(get_ctx)):
    config = ctx.cfg()
    roots = [{"label": f"源目录: {s}", "path": str(Path(s).resolve())}
             for s in config.source_dirs]
    roots.append({"label": f"媒体库: {config.library_dir}",
                  "path": str(Path(config.library_dir).resolve())})
    return {"roots": roots}


@router.get("/files")
def api_files_list(path: str, ctx: WebContext = Depends(get_ctx)):
    base = safe_path(ctx, path)
    if not base.is_dir():
        raise HTTPException(400, "不是目录")
    entries: List[dict] = []
    for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
        except OSError:
            continue
    return {"path": str(base), "parent": str(base.parent), "entries": entries}


@router.post("/files/delete")
def api_files_delete(body: DeleteBody, ctx: WebContext = Depends(get_ctx)):
    p = safe_path(ctx, body.path, allow_root=False)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    except OSError as e:
        raise HTTPException(500, f"删除失败: {e}")
    return {"ok": True}


@router.post("/files/rename")
def api_files_rename(body: RenameBody, ctx: WebContext = Depends(get_ctx)):
    p = safe_path(ctx, body.path, allow_root=False)
    if "/" in body.name or "\\" in body.name or body.name in ("", ".", ".."):
        raise HTTPException(400, "非法的新名称")
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    new = safe_path(ctx, str(p.parent / body.name))
    if new.exists():
        raise HTTPException(409, "目标已存在")
    try:
        os.replace(p, new)
    except OSError as e:
        raise HTTPException(500, f"重命名失败: {e}")
    return {"ok": True, "path": str(new)}
