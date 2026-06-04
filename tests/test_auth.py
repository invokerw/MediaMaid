from pathlib import Path

from mediamaid.config import Config
from mediamaid.pipeline import build_notifiers
from mediamaid.web import auth


def test_hash_verify_password():
    h = auth.hash_password("secret")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("secret", h)
    assert not auth.verify_password("wrong", h)


def test_empty_hash_uses_default_admin():
    # password_hash 为空 → 默认口令 admin
    assert auth.verify_password("admin", "")
    assert not auth.verify_password("other", "")


def test_token_lifecycle():
    t = auth.issue_token()
    assert auth.check_token(t)
    auth.revoke_token(t)
    assert not auth.check_token(t)
    assert not auth.check_token("nope")
    assert not auth.check_token(None)


def test_build_notifiers_always_includes_log(tmp_path):
    cfg = Config(source_dirs=[tmp_path], library_dir=tmp_path / "lib", plugins={})
    names = [n.name for n in build_notifiers(cfg)]
    assert "log" in names  # 未配置也内置常开
