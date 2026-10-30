import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import database, models
from app.config.templates import templates
from app.email_utils import send_password_reset_email
from app.services.accounts import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.services.rate_limit import enforce_rate_limit, limit_key

router = APIRouter(tags=["PasswordReset"])
logger = logging.getLogger(__name__)

RESET_REQUEST_LIMIT = 5
RESET_REQUEST_WINDOW_SECONDS = 3600


def _now_utc() -> datetime:
    # 使用 naive UTC 时间，避免与数据库返回的 naive datetime 比较时报错
    return datetime.utcnow()


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
    enforce_rate_limit(
        request,
        key=limit_key(request, "password-reset"),
        limit=RESET_REQUEST_LIMIT,
        window_seconds=RESET_REQUEST_WINDOW_SECONDS,
    )

    now = _now_utc()
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.expires_at < now
    ).delete(synchronize_session=False)
    db.commit()

    user = (
        db.query(models.User)
        .filter(func.lower(models.User.email) == (email or "").strip().lower())
        .first()
    )

    if user:
        # 为该用户创建一次性 token（有效期 30 分钟），数据库只保存哈希
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(minutes=30)

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token=_hash_reset_token(token),
            expires_at=expires_at,
        )
        db.add(reset_token)
        db.commit()

        try:
            await send_password_reset_email(email=user.email, token=token)
        except Exception:
            logger.exception("发送密码重置邮件失败")

    # 无论是否存在该邮箱，都渲染同一结果页面
    return templates.TemplateResponse(
        "password_reset_request_done.html",
        {"request": request},
    )


def _get_valid_reset_token(db: Session, token: str) -> models.PasswordResetToken:
    """根据 token 查询并校验是否有效（存在且未过期）。"""
    token_value = (token or "").strip()
    reset_token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token == _hash_reset_token(token_value))
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

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return templates.TemplateResponse(
            "password_reset_form.html",
            {
                "request": request,
                "token": token,
                "error_message": f"密码至少需要 {PASSWORD_MIN_LENGTH} 位。",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(new_password) > PASSWORD_MAX_LENGTH:
        return templates.TemplateResponse(
            "password_reset_form.html",
            {
                "request": request,
                "token": token,
                "error_message": f"密码不能超过 {PASSWORD_MAX_LENGTH} 位。",
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

    # 更新用户密码，吊销已有 JWT，并使所有未使用的重置链接失效
    user.hashed_password = get_password_hash(new_password)
    user.token_version = (user.token_version or 0) + 1
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id
    ).delete(synchronize_session=False)
    db.commit()

    return templates.TemplateResponse(
        "password_reset_success.html",
        {"request": request},
    )


