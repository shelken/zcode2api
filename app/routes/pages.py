"""页面路由：登录、账号管理、设置。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from .. import settings
from ..oauth import _codes

router = APIRouter()

_TOKEN = "{{APP_VERSION}}"


@router.get("/admin/api/login/callback", include_in_schema=False)
async def oauth_callback(code: str, state: str):
    """OAuth 回调（免鉴权）：浏览器授权后 redirect 回此端点，存 code 供轮询兑换。"""
    if not code or not state:
        return JSONResponse({"status": "failed", "message": "缺少 code/state"}, status_code=400)
    _codes[state] = code
    return JSONResponse({"status": "ok", "message": "授权成功，请回到后台页面查看"})


def _html(name: str) -> HTMLResponse:
    path = settings.STATIC_DIR / "admin" / name
    if not path.exists():
        raise HTTPException(404, "页面不存在")
    body = path.read_text(encoding="utf-8").replace(_TOKEN, settings.APP_VERSION)
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/admin")


@router.get("/admin", include_in_schema=False)
async def admin_root():
    return RedirectResponse("/admin/login")


@router.get("/admin/login", include_in_schema=False)
async def admin_login():
    return _html("login.html")


@router.get("/admin/accounts", include_in_schema=False)
async def admin_accounts():
    return _html("accounts.html")


@router.get("/admin/settings", include_in_schema=False)
async def admin_settings():
    return _html("settings.html")


@router.get("/meta", include_in_schema=False)
async def meta():
    return {"version": settings.APP_VERSION}
