from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from app.routers import ratings
from . import models, database, auth
from .routers import authentication, pages, api, admin, articles, bounties, password_reset, resources
from starlette.middleware.sessions import SessionMiddleware
import secrets
import os
from app.config.constants import BASE_DIR
from app.config.site_config import get_site_config
from jose import jwt

# 创建所有数据库表
models.Base.metadata.create_all(bind=database.engine)

# 初始化悬赏板块
def init_bounty_categories():
    """初始化预设的悬赏板块"""
    db = database.SessionLocal()
    try:
        # 检查是否已有板块
        existing = db.query(models.BountyCategory).first()
        if existing:
            return  # 已初始化，跳过
        
        # 创建预设板块
        categories = [
            models.BountyCategory(name="技术求助", description="技术问题求助、代码实现等"),
            models.BountyCategory(name="资源征集", description="游戏资源、素材、资料征集"),
            models.BountyCategory(name="合作邀请", description="项目合作、团队招募等"),
            models.BountyCategory(name="其他", description="其他类型的悬赏"),
            models.BountyCategory(name="游戏悬赏", description="游戏相关悬赏")
        ]
        
        for category in categories:
            db.add(category)
        
        db.commit()
        print("悬赏板块初始化完成")
    except Exception as e:
        db.rollback()
        print(f"初始化悬赏板块时出错: {e}")
    finally:
        db.close()

# 初始化悬赏板块
init_bounty_categories()

# 从配置读取应用标题
site_config = get_site_config()
app_title = site_config.get("app_title", "STG Community Ratings")
app = FastAPI(title=app_title)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# 挂载静态文件目录（使用绝对路径，避免路径问题）
# BASE_DIR 已经是项目根目录，所以直接使用 app/static
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

# 添加 SessionMiddleware
# 从环境变量读取会话密钥，如果未设置则生成随机密钥（仅用于开发）
SESSION_SECRET_KEY = os.getenv("STG_SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    SESSION_SECRET_KEY = secrets.token_urlsafe(32)

# 从环境变量读取HTTPS设置，生产环境应设为True
HTTPS_ONLY = os.getenv("STG_HTTPS_ONLY", "False").lower() == "true"

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="session_id",
    max_age=3600 * 24 * 7,  # 会话有效期 7 天
    same_site="lax",
    https_only=HTTPS_ONLY
)

# 中间件：在每个请求中检查cookie，并将用户信息附加到request.state
# 这是为了模板可以访问 request.state.user
@app.middleware("http")
async def add_user_to_state(request: Request, call_next):
    """将用户信息附加到 request.state，供模板使用"""
    request.state.user = None
    token = request.cookies.get("access_token")
    if token:
        try:
            # 移除可能的 "Bearer " 前缀
            token = token[7:] if token.startswith("Bearer ") else token
            payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            username: str = payload.get("sub")
            if username:
                db = database.SessionLocal()
                try:
                    user = auth.get_user(db, username)
                    if user:
                        request.state.user = user
                finally:
                    db.close()
        except Exception:
            # Token 无效或过期，忽略错误，保持 request.state.user = None
            pass
    response = await call_next(request)
    return response

# 包含来自其他文件的路由
app.include_router(authentication.router)
app.include_router(pages.router)
app.include_router(api.router)
app.include_router(ratings.router)
app.include_router(admin.router) # +++ 包含新的 admin 路由
app.include_router(articles.router)
app.include_router(bounties.router)
app.include_router(password_reset.router)
app.include_router(resources.router)