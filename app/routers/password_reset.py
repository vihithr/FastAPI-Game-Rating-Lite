import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import database, models
from app.config.templates import templates
from app.email_utils import send_password_reset_email

router = APIRouter(tags=["PasswordReset"])


def _now_utc() -> datetime:
    # 使用 naive UTC 时间，避免与数据库返回的 naive datetime 比较时报错
    return datetime.utcnow()


@router.get("/password-reset-request")
def get_password_reset_request_form(request: Request):
    """显示输入邮箱的密码重置请求页面"""
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request},
    )


@router.post("/password-reset/request")
async def request_password_reset(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(database.get_db),
):
    """
    处理用户提交邮箱的密码重置请求。
    无论邮箱是否存在，都返回统一的提示，避免泄露用户信息。
    """
    user = db.query(models.User).filter(models.User.email == email).first()

    if user:
        # 为该用户创建一次性 token（有效期 30 分钟）
        token = secrets.token_urlsafe(32)
        expires_at = _now_utc() + timedelta(minutes=30)

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
        )
        db.add(reset_token)
        db.commit()

        # 异步发送邮件
        await send_password_reset_email(email=user.email, token=token)

    # 无论是否存在该邮箱，都渲染同一结果页面
    return templates.TemplateResponse(
        "password_reset_request_done.html",
        {"request": request},
    )


def _get_valid_reset_token(db: Session, token: str) -> models.PasswordResetToken:
    """根据 token 查询并校验是否有效（存在且未过期）。"""
    reset_token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token == token)
        .first()
    )
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置链接无效或已被使用。",
        )

    if reset_token.expires_at < _now_utc():
        # 过期后直接删除记录
        db.delete(reset_token)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置链接已过期，请重新申请。",
        )

    return reset_token


@router.get("/password-reset")
def get_password_reset_form(request: Request, token: str, db: Session = Depends(database.get_db)):
    """
    打开密码重置表单页面。
    如果 token 无效或过期，展示错误信息。
    """
    try:
        _get_valid_reset_token(db, token)
    except HTTPException as exc:
        # 将错误信息展示在单独页面
        return templates.TemplateResponse(
            "password_reset_error.html",
            {"request": request, "error_message": exc.detail},
            status_code=exc.status_code,
        )

    return templates.TemplateResponse(
        "password_reset_form.html",
        {"request": request, "token": token},
    )


@router.post("/password-reset")
def submit_new_password(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db),
):
    """提交新密码并完成重置。"""
    from app.auth import get_password_hash  # 延迟导入避免循环引用

    if new_password != confirm_password:
        return templates.TemplateResponse(
            "password_reset_form.html",
            {
                "request": request,
                "token": token,
                "error_message": "两次输入的密码不一致。",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        reset_token = _get_valid_reset_token(db, token)
    except HTTPException as exc:
        return templates.TemplateResponse(
            "password_reset_error.html",
            {"request": request, "error_message": exc.detail},
            status_code=exc.status_code,
        )

    user = db.query(models.User).filter(models.User.id == reset_token.user_id).first()
    if not user:
        # 如果出现异常情况（token 对应用户不存在），也直接删除 token
        db.delete(reset_token)
        db.commit()
        return templates.TemplateResponse(
            "password_reset_error.html",
            {"request": request, "error_message": "用户不存在。"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 更新用户密码
    user.hashed_password = get_password_hash(new_password)
    # 重置成功后物理删除 token 记录
    db.delete(reset_token)
    db.commit()

    return templates.TemplateResponse(
        "password_reset_success.html",
        {"request": request},
    )


