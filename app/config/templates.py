from fastapi.templating import Jinja2Templates
from app.config.constants import BASE_DIR
from app.config.site_config import get_site_config

# 使用绝对路径配置模板目录，避免路径问题
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# 为模板环境添加全局变量，使所有模板都能访问站点配置
site_config = get_site_config()
templates.env.globals["site_config"] = site_config
