from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from app.config.templates import templates as jinja_templates
from app.routers import ratings
from . import models, database, auth
from .routers import authentication, pages, api, admin, articles, bounties, password_reset, resources, library
from contextlib import asynccontextmanager
import logging
from app.config.constants import BASE_DIR, SITE_BASE_URL
from app.core.middleware import SameOriginMiddleware, StaticCacheMiddleware
from jose import jwt

logger = logging.getLogger(__name__)

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
        logger.info("悬赏板块初始化完成")
    except Exception:
        db.rollback()
        logger.exception("初始化悬赏板块时出错")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=database.engine)
    init_bounty_categories()
    yield


app = FastAPI(title="STG Community Ratings", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# 挂载静态文件目录（使用绝对路径，避免路径问题）
# BASE_DIR 已经是项目根目录，所以直接使用 app/static
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

app.add_middleware(SameOriginMiddleware, site_base_url=SITE_BASE_URL)
app.add_middleware(StaticCacheMiddleware)

# 中间件：在每个请求中检查cookie，并将用户信息附加到request.state
# 这是为了模板可以访问 request.state.user
@app.middleware("http")
async def add_user_to_state(request: Request, call_next):
    """将用户信息附加到 request.state，供模板使用"""
    if request.url.path.startswith("/static/"):
        return await call_next(request)
    request.state.user = None
    token = request.cookies.get("access_token")
    if token:
        try:
            # 移除可能的 "Bearer " 前缀
            token = token[7:] if token.startswith("Bearer ") else token
            payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            username: str = payload.get("sub")
            token_version = int(payload.get("ver", 0))
            if username:
                db = database.SessionLocal()
                try:
                    user = auth.get_user(db, username)
                    if user and user.token_version == token_version:
                        request.state.user = user
                finally:
                    db.close()
        except Exception:
            # Token 无效或过期，忽略错误，保持 request.state.user = None
            pass
    response = await call_next(request)
    return response


# HTML 请求返回友好错误页，API 请求保持 JSON
@app.exception_handler(StarletteHTTPException)
async def friendly_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) else "页面出错了"
    return jinja_templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": exc.status_code, "detail": detail},
        status_code=exc.status_code,
    )


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
app.include_router(library.router)