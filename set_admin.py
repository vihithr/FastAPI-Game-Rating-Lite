# set_admin.py
import sys
from app import models, database

def set_user_admin_status(username: str, is_admin: bool):
    """设置用户的管理员状态"""
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            print(f"错误：找不到用户 '{username}'")
            return

        user.is_admin = is_admin
        db.commit()
        status = "管理员" if is_admin else "普通用户"
        print(f"成功将用户 '{username}' 的状态设置为 {status}。")

    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python set_admin.py <用户名> <true|false>")
        sys.exit(1)

    target_username = sys.argv[1]
    should_be_admin = sys.argv[2].lower() == 'true'

    set_user_admin_status(target_username, should_be_admin)