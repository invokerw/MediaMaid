"""Web 登录鉴权：密码哈希 + 内存 token（单账号）。

口令哈希用 pbkdf2_sha256 + 随机盐（仅标准库）。password_hash 为空时按默认口令
'admin' 校验，保证开箱即用；用户改过密码后即存哈希。会话 token 存进程内存，
重启后失效需重新登录。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

_DEFAULT_PASSWORD = "admin"
_ITERATIONS = 200_000
_TOKEN_TTL = 7 * 24 * 3600  # 7 天

# token -> 过期时间戳
_tokens: dict[str, float] = {}


def hash_password(password: str) -> str:
    """返回 'pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>'。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验口令。stored 为空 → 按默认口令 'admin' 比较。"""
    if not stored:
        return hmac.compare_digest(password, _DEFAULT_PASSWORD)
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def issue_token() -> str:
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + _TOKEN_TTL
    return token


def check_token(token: str) -> bool:
    exp = _tokens.get(token)
    if exp is None:
        return False
    if exp < time.time():
        _tokens.pop(token, None)
        return False
    return True


def revoke_token(token: str) -> None:
    _tokens.pop(token, None)


def bearer_token(authorization: str | None) -> str | None:
    """从 'Bearer <token>' 头提取 token。"""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None
