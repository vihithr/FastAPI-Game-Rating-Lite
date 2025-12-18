from pathlib import Path
import os

# 获取应用根目录（app目录的父目录，即项目根目录）
# __file__ 是 app/config/constants.py，所以需要向上3级到达项目根目录
BASE_DIR = Path(__file__).parent.parent.parent

# 浏览页面标签显示上限（只显示最常用的标签）
MAX_TAGS_DISPLAY = int(os.getenv("STG_MAX_TAGS_DISPLAY", "50"))

# 邮件与站点相关配置（用于密码重置等功能）
SITE_BASE_URL = os.getenv("STG_SITE_BASE_URL", "http://localhost:8000/")

# 使用 fastapi-mail 发送邮件时的基础配置（从环境变量读取）
MAIL_USERNAME = os.getenv("STG_MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("STG_MAIL_PASSWORD", "")
MAIL_FROM = os.getenv("STG_MAIL_FROM", "")
MAIL_PORT = int(os.getenv("STG_MAIL_PORT", "465"))
MAIL_SERVER = os.getenv("STG_MAIL_SERVER", "smtp.qq.com")
MAIL_TLS = os.getenv("STG_MAIL_TLS", "False").lower() == "true"
MAIL_SSL = os.getenv("STG_MAIL_SSL", "True").lower() == "true"
MAIL_USE_CREDENTIALS = os.getenv("STG_MAIL_USE_CREDENTIALS", "True").lower() == "true"
