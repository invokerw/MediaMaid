"""登录鉴权：登录/登出/当前用户/改账号（单账号）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import auth, cfgio
from ..deps import WebContext, get_ctx
from ..schemas import AccountBody, LoginBody

router = APIRouter(prefix="/api")


@router.post("/login")
def api_login(body: LoginBody, ctx: WebContext = Depends(get_ctx)):
    acc = ctx.cfg().auth
    if not auth.verify_login(body.username, body.password, acc.username, acc.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {"token": auth.issue_token(), "username": auth.effective_username(acc.username)}


@router.post("/logout")
def api_logout(authorization: str | None = Header(default=None)):
    tok = auth.bearer_token(authorization)
    if tok:
        auth.revoke_token(tok)
    return {"ok": True}


@router.get("/me")
def api_me(ctx: WebContext = Depends(get_ctx)):
    # 能到这里说明已过中间件鉴权
    acc = ctx.cfg().auth
    return {"username": auth.effective_username(acc.username), "env_managed": auth.env_managed()}


@router.put("/account")
def api_account(body: AccountBody, ctx: WebContext = Depends(get_ctx)):
    if auth.env_managed():
        raise HTTPException(400, "账号由环境变量（MEDIAMAID_USERNAME/PASSWORD）管理，无法在此修改")
    acc = ctx.cfg().auth
    if not auth.verify_password(body.current_password, acc.password_hash):
        raise HTTPException(403, "当前密码不正确")
    new_auth = {"username": acc.username, "password_hash": acc.password_hash}
    if body.username:
        new_auth["username"] = body.username
    if body.password:
        new_auth["password_hash"] = auth.hash_password(body.password)
    cfgio.update_settings(ctx.config_path, {"auth": new_auth})
    cfg = ctx.manager.reload()
    return {"username": cfg.auth.username}
