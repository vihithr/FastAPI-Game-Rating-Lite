from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
import os

# 这里显式兼容不同版本的 bcrypt，避免 passlib 自检时出错
try:
    import bcrypt as _bcrypt  # type: ignore
    # 新版 bcrypt 删除了 __about__，而 passlib 仍然依赖它来获取版本号
    if not hasattr(_bcrypt, "__about__"):
        class _About:  # 简单的兼容壳
            __version__ = getattr(_bcrypt, "__version__", "4.0")

        _bcrypt.__about__ = _About()  # type: ignore[attr-defined]
except Exception:
    # 如果环境里没有 bcrypt 或其他异常，交给 passlib 自己处理
    _bcrypt = None  # type: ignore[assignment]

from . import models, database

# 安全配置
SECRET_KEY = os.getenv("STG_SECRET_KEY", "a_very_very_secret_key_should_be_in_env_var")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("STG_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 默认24小时 

# 说明：
# - bcrypt 原生只支持前 72 字节的密码（按字节算，不是字符）
# - 旧环境一般是「静默截断」，不会抛错；新版本组合会在自检时直接 raise ValueError
# - 这里采用两层方案：
#   1）新生成的密码用 bcrypt_sha256（先做 sha256，再用 bcrypt），自然不会触到 72 字节限制
#   2）保留纯 bcrypt，用于兼容老数据库里的哈希
#   3）关闭 truncate_error，保持「过长时自动截断」而不是抛异常，更鲁棒
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,
)


class CookieOrBearerAuth(HTTPBearer):
    """支持从 Cookie 或 Authorization 头部获取 token 的认证类"""
    async def __call__(self, request: Request) -> Optional[str]:
        # 优先检查 Cookie 中的 token
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            # 移除可能的 "Bearer " 前缀
            return cookie_token[7:] if cookie_token.startswith("Bearer ") else cookie_token
        
        # 回退到 Authorization 头部
        try:
            auth_header = await super().__call__(request)
            return auth_header.credentials
        except HTTPException:
            return None

cookie_auth = CookieOrBearerAuth()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_user(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

async def get_current_user(
    token: str = Depends(cookie_auth),  # 使用自定义的认证方式
    db: Session = Depends(database.get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    if user := get_user(db, username=username):
        return user
    raise credentials_exception

async def get_current_admin_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    验证当前用户是否为管理员。
    如果不是管理员，则抛出 403 Forbidden 错误。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有足够权限执行此操作，需要管理员身份。",
        )
    return current_user
