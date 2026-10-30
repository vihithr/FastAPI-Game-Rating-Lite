import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import auth, database
from app.config.templates import templates
from app.services.accounts import create_user
from app.services.flash import redirect_with_flash
from app.services.rate_limit import (
    enforce_rate_limit,
    limit_key,
    limiter,
)

router = APIRouter(
    tags=["Authentication"] # 在API文档中分组
)

COOKIE_SECURE = os.getenv("STG_HTTPS_ONLY", "False").lower() == "true"
LOGIN_USER_LIMIT = 10
LOGIN_USER_WINDOW_SECONDS = 300
LOGIN_IP_LIMIT = 50
LOGIN_IP_WINDOW_SECONDS = 300
REGISTER_LIMIT = 5
REGISTER_WINDOW_SECONDS = 3600


def safe_redirect_target(value: str | None) -> str:
    """仅接受站内相对路径，防止开放重定向。"""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


@router.get("/register", response_class=RedirectResponse)
def get_register_form(request: Request):
    """显示注册表单页面"""
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
def register_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    """处理用户注册逻辑"""
    try:
        enforce_rate_limit(
            request,
            key=limit_key(request, "register"),
            limit=REGISTER_LIMIT,
            window_seconds=REGISTER_WINDOW_SECONDS,
        )
        create_user(db, username, email, password)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "注册失败，请稍后再试"
        return redirect_with_flash("/register", "error", detail)
    return redirect_with_flash("/login", "success", "注册成功，请登录")

@router.get("/login", response_class=RedirectResponse)
def get_login_form(request: Request, redirect: str = None):
    """显示登录表单页面"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "redirect_target": safe_redirect_target(redirect) if redirect else "",
    })

@router.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    redirect: str = Form(""),
    db: Session = Depends(database.get_db)
):
    target = safe_redirect_target(redirect)
    try:
        login_ip_key = limit_key(request, "login-ip")
        login_user_key = limit_key(request, "login", username)
        enforce_rate_limit(
            request,
            key=login_ip_key,
            limit=LOGIN_IP_LIMIT,
            window_seconds=LOGIN_IP_WINDOW_SECONDS,
        )
        enforce_rate_limit(
            request,
            key=login_user_key,
            limit=LOGIN_USER_LIMIT,
            window_seconds=LOGIN_USER_WINDOW_SECONDS,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "请求过于频繁，请稍后再试"
        return redirect_with_flash("/login", "error", detail)

    user = auth.authenticate_user(db, username, password)
    if not user:
        return redirect_with_flash("/login", "error", "用户名或密码错误")

    limiter.clear(login_user_key)

    access_token = auth.create_access_token(
        data={"sub": user.username, "ver": user.token_version}
    )
    response = redirect_with_flash(target, "success", f"欢迎回来，{user.username}")
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response

@router.get("/logout")
def logout_user():
    """处理用户登出逻辑，删除Cookie"""
    response = redirect_with_flash("/", "info", "已登出")
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response
