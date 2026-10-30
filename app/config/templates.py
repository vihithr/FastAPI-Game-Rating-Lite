from functools import lru_cache

from fastapi.templating import Jinja2Templates

from app.config.constants import BASE_DIR
from app.services.uploads import cover_thumbnail_url

# 使用绝对路径配置模板目录，避免路径问题
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@lru_cache(maxsize=64)
def asset_url(path: str) -> str:
    if not path.startswith("/static/"):
        return path
    static_path = BASE_DIR / "app" / path.lstrip("/")
    try:
        version = int(static_path.stat().st_mtime)
    except OSError:
        return path
    return f"{path}?v={version}"


templates.env.globals["asset_url"] = asset_url
templates.env.globals["cover_thumb"] = cover_thumbnail_url
