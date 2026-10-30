from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, models

USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def create_user(db: Session, username: str, email: str, password: str) -> models.User:
    """校验注册输入并创建用户；所有失败都以 400 返回。"""
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(username) > USERNAME_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"用户名不能超过 {USERNAME_MAX_LENGTH} 个字符")

    try:
        normalized_email = validate_email(
            (email or "").strip(), check_deliverability=False
        ).normalized
    except EmailNotValidError:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"密码至少需要 {PASSWORD_MIN_LENGTH} 位"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"密码不能超过 {PASSWORD_MAX_LENGTH} 位"
        )

    if db.query(models.User.id).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已被注册")
    if (
        db.query(models.User.id)
        .filter(func.lower(models.User.email) == normalized_email.lower())
        .first()
    ):
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = models.User(
        username=username,
        email=normalized_email,
        hashed_password=auth.get_password_hash(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")
    db.refresh(user)
    return user
