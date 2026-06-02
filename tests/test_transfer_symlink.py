"""软链接传输动作。"""

import os

from mediamaid.models import TransferAction
from mediamaid.transfer import transfer


def test_symlink_creates_link_to_source(tmp_path):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"x" * 100)
    dest = tmp_path / "lib" / "out.mkv"
    written = transfer(src, dest, TransferAction.SYMLINK)
    assert written.is_symlink()
    assert os.readlink(written) == str(src.resolve())
    # 通过软链接能读到源内容
    assert written.read_bytes() == b"x" * 100


def test_symlink_skip_on_conflict(tmp_path):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"x" * 100)
    dest = tmp_path / "lib" / "out.mkv"
    transfer(src, dest, TransferAction.SYMLINK)
    # 已存在 + skip → 返回 None
    assert transfer(src, dest, TransferAction.SYMLINK, on_conflict="skip") is None
