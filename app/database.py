from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

# 从环境变量读取数据库URL，如果未设置则使用默认路径
# 默认路径使用绝对路径，避免工作目录问题
DEFAULT_DB_PATH = Path(__file__).parent.parent / "stg_website.db"
SQLALCHEMY_DATABASE_URL = os.getenv("STG_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.absolute()}")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 添加这个函数
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)
