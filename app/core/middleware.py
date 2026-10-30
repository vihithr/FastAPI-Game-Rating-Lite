from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LONG_CACHE_PREFIXES = (
    "/static/uploads/",
    "/static/css/",
    "/static/js/",
    "/static/vendor/",
)


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """Set cache headers: long-lived for versioned static assets, no-cache for pages."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            if response.status_code != 200:
                return response
            if path.startswith(LONG_CACHE_PREFIXES):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "public, max-age=3600"
        elif "Cache-Control" not in response.headers:
            # 动态页面禁止启发式缓存，避免浏览器展示旧 HTML
            response.headers["Cache-Control"] = "no-cache"
        return response


class SameOriginMiddleware(BaseHTTPMiddleware):
    """Reject cookie-authenticated cross-origin state changes."""

    def __init__(self, app, site_base_url: str = ""):
        super().__init__(app)
        self.allowed_hosts = set()
        site_host = urlparse(site_base_url).netloc.lower()
        if site_host:
            self.allowed_hosts.add(site_host)

    async def dispatch(self, request: Request, call_next):
        if (
            request.method in UNSAFE_METHODS
            and request.cookies.get("access_token")
        ):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin:
                origin_host = urlparse(origin).netloc.lower()
                request_host = request.headers.get("host", "").lower()
                allowed = set(self.allowed_hosts)
                if request_host:
                    allowed.add(request_host)
                if not origin_host or origin_host not in allowed:
                    return JSONResponse(
                        {"detail": "跨站请求被拒绝"}, status_code=403
                    )
        return await call_next(request)
