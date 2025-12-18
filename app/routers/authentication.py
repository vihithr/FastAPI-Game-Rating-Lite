from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import auth, models, schemas, database
from app.config.templates import templates  # 直接从模板配置导入

router = APIRouter(
    tags=["Authentication"] # 在API文档中分组
)

@router.get("/register", response_class=RedirectResponse)
def get_register_form(request: Request):
    """显示注册表单页面"""
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
def register_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    """处理用户注册逻辑"""
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = auth.get_password_hash(password)
    new_user = models.User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/login", response_class=RedirectResponse)
def get_login_form(request: Request):
    """显示登录表单页面"""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login_user(
    request: Request,  # 添加 request 参数
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user = auth.authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth.create_access_token(data={"sub": user.username})
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite='lax')
    
    # 设置会话用户ID
    request.session["user_id"] = user.id
    
    return response

@router.get("/logout")
def logout_user(request: Request):  # 添加 request 参数
    """处理用户登出逻辑，删除Cookie和会话"""
    # 清除会话
    request.session.clear()
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response