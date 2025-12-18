from fastapi.templating import Jinja2Templates
from app.config.constants import BASE_DIR

# 使用绝对路径配置模板目录，避免路径问题
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
