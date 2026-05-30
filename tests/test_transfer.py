import os
from pathlib import Path

from mediamaid import transfer
from mediamaid.models import TransferAction


def _make_src(tmp_path: Path, content=b"hello world") -> Path:
    src = tmp_path / "src" / "movie.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(content)
    return src


def test_hardlink(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    out = transfer.transfer(src, dest, TransferAction.HARDLINK)
    assert out == dest
    assert dest.exists()
    # 硬链接：同一 inode
    assert src.stat().st_ino == dest.stat().st_ino


def test_copy_keeps_source(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    transfer.transfer(src, dest, TransferAction.COPY)
    assert src.exists() and dest.exists()
    assert src.stat().st_ino != dest.stat().st_ino
    assert dest.read_bytes() == b"hello world"
    # 不应残留临时文件
    assert not (dest.parent / (dest.name + ".mmpart")).exists()


def test_move_removes_source(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    transfer.transfer(src, dest, TransferAction.MOVE)
    assert not src.exists()
    assert dest.exists()


def test_dry_run_no_change(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    out = transfer.transfer(src, dest, TransferAction.HARDLINK, dry_run=True)
    assert out == dest
    assert not dest.exists()


def test_conflict_skip(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"existing")
    out = transfer.transfer(src, dest, TransferAction.COPY, on_conflict="skip")
    assert out is None
    assert dest.read_bytes() == b"existing"


def test_conflict_rename(tmp_path):
    src = _make_src(tmp_path)
    dest = tmp_path / "lib" / "movie.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"existing")
    out = transfer.transfer(src, dest, TransferAction.COPY, on_conflict="rename")
    assert out == tmp_path / "lib" / "movie (1).mkv"
    assert out.exists()
