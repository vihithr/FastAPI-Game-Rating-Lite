from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from sqlalchemy.orm import Session, selectinload
from fastapi.responses import RedirectResponse, HTMLResponse
from .. import models, database, auth
from app.config.templates import templates

router = APIRouter(
    tags=["Bounties"]
)

# --- 公开路由 ---

@router.get("/bounties", response_class=HTMLResponse)
def list_bounties(
    request: Request,
    db: Session = Depends(database.get_db),
    category_id: int = None,
    status_filter: str = "all"  # all, active, completed
):
    """悬赏列表页"""
    query = db.query(models.Bounty).options(
        selectinload(models.Bounty.creator),
        selectinload(models.Bounty.category),
        selectinload(models.Bounty.bounty_tags),
        selectinload(models.Bounty.comments)
    )
    
    # 按板块筛选
    if category_id is not None:
        query = query.filter(models.Bounty.category_id == category_id)
    
    # 按状态筛选
    if status_filter == "active":
        query = query.filter(models.Bounty.is_completed == False)
    elif status_filter == "completed":
        query = query.filter(models.Bounty.is_completed == True)
    
    # 按创建时间倒序
    bounties = query.order_by(models.Bounty.created_at.desc()).all()
    
    # 获取所有板块
    categories = db.query(models.BountyCategory).order_by(models.BountyCategory.name).all()
    
    return templates.TemplateResponse("bounties_list.html", {
        "request": request,
        "bounties": bounties,
        "categories": categories,
        "current_category_id": category_id,
        "current_status": status_filter
    })


# --- 需要登录的路由 ---

@router.get("/bounty/new", response_class=HTMLResponse)
def new_bounty_form(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """创建悬赏表单"""
    categories = db.query(models.BountyCategory).order_by(models.BountyCategory.name).all()
    return templates.TemplateResponse("bounty_form.html", {
        "request": request,
        "bounty": None,
        "categories": categories,
        "action": "create"
    })


@router.post("/bounty/new", response_class=RedirectResponse)
def create_bounty(
    title: str = Form(...),
    content: str = Form(...),
    reward: str = Form(...),
    game_name: str = Form(None),
    category_id: int = Form(...),
    contact_info: str = Form(None),
    tags: str = Form(""),  # 以 |~| 分隔的标签字符串
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """提交新悬赏"""
    # 验证板块是否存在
    category = db.query(models.BountyCategory).filter(models.BountyCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="无效的悬赏板块")
    
    bounty = models.Bounty(
        title=title,
        content=content,
        reward=reward,
        game_name=game_name if game_name else None,
        created_by=current_user.id,
        category_id=category_id,
        contact_info=contact_info
    )
    
    # 处理悬赏标签
    if tags:
        tag_names = {name.strip() for name in tags.split('|~|') if name.strip()}
        existing_tags = db.query(models.BountyTag).filter(models.BountyTag.name.in_(tag_names)).all()
        existing_tag_names = {tag.name for tag in existing_tags}
        bounty.bounty_tags.extend(existing_tags)
        for name in tag_names - existing_tag_names:
            new_tag = models.BountyTag(name=name)
            db.add(new_tag)
            bounty.bounty_tags.append(new_tag)
    
    db.add(bounty)
    db.commit()
    db.refresh(bounty)
    
    return RedirectResponse(url=f"/bounty/{bounty.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/bounty/{bounty_id}", response_class=HTMLResponse)
def bounty_detail(
    bounty_id: int,
    request: Request,
    db: Session = Depends(database.get_db)
):
    """悬赏详情页"""
    bounty = db.query(models.Bounty).options(
        selectinload(models.Bounty.creator),
        selectinload(models.Bounty.category),
        selectinload(models.Bounty.bounty_tags),
        selectinload(models.Bounty.comments).selectinload(models.BountyComment.author)
    ).filter(models.Bounty.id == bounty_id).first()
    
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    # 检查是否为发布者或管理员
    is_owner = request.state.user and request.state.user.id == bounty.created_by
    is_admin = request.state.user and request.state.user.is_admin
    can_edit = is_owner or is_admin
    
    return templates.TemplateResponse("bounty_detail.html", {
        "request": request,
        "bounty": bounty,
        "can_edit": can_edit,
        "is_owner": is_owner
    })


@router.get("/bounty/{bounty_id}/edit", response_class=HTMLResponse)
def edit_bounty_form(
    bounty_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """编辑悬赏表单"""
    bounty = db.query(models.Bounty).options(
        selectinload(models.Bounty.bounty_tags)
    ).filter(models.Bounty.id == bounty_id).first()
    
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    # 检查权限
    if bounty.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限编辑此悬赏")
    
    categories = db.query(models.BountyCategory).order_by(models.BountyCategory.name).all()
    
    return templates.TemplateResponse("bounty_form.html", {
        "request": request,
        "bounty": bounty,
        "categories": categories,
        "action": "edit"
    })


@router.post("/bounty/{bounty_id}/edit", response_class=RedirectResponse)
def update_bounty(
    bounty_id: int,
    title: str = Form(...),
    content: str = Form(...),
    reward: str = Form(...),
    game_name: str = Form(None),
    category_id: int = Form(...),
    contact_info: str = Form(None),
    tags: str = Form(""),  # 以 |~| 分隔的标签字符串
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """更新悬赏"""
    bounty = db.query(models.Bounty).options(
        selectinload(models.Bounty.bounty_tags)
    ).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    # 检查权限
    if bounty.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限编辑此悬赏")
    
    # 验证板块是否存在
    category = db.query(models.BountyCategory).filter(models.BountyCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="无效的悬赏板块")
    
    bounty.title = title
    bounty.content = content
    bounty.reward = reward
    bounty.game_name = game_name if game_name else None
    bounty.category_id = category_id
    bounty.contact_info = contact_info
    
    # 处理悬赏标签
    bounty.bounty_tags.clear()
    if tags:
        tag_names = {name.strip() for name in tags.split('|~|') if name.strip()}
        existing_tags = db.query(models.BountyTag).filter(models.BountyTag.name.in_(tag_names)).all()
        existing_tag_names = {tag.name for tag in existing_tags}
        bounty.bounty_tags.extend(existing_tags)
        for name in tag_names - existing_tag_names:
            new_tag = models.BountyTag(name=name)
            db.add(new_tag)
            bounty.bounty_tags.append(new_tag)
    
    db.commit()
    
    return RedirectResponse(url=f"/bounty/{bounty_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bounty/{bounty_id}/complete", response_class=RedirectResponse)
def complete_bounty(
    bounty_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """标记悬赏为已完成"""
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    # 检查权限
    if bounty.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限完成此悬赏")
    
    from datetime import datetime, timezone
    bounty.is_completed = True
    bounty.completed_at = datetime.now(timezone.utc)
    
    db.commit()
    
    return RedirectResponse(url=f"/bounty/{bounty_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bounty/{bounty_id}/comment", response_class=RedirectResponse)
def add_bounty_comment(
    bounty_id: int,
    content: str = Form(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """添加悬赏评论"""
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    if not content.strip():
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    
    comment = models.BountyComment(
        bounty_id=bounty_id,
        author_id=current_user.id,
        content=content.strip()
    )
    
    db.add(comment)
    db.commit()
    
    return RedirectResponse(url=f"/bounty/{bounty_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bounty/{bounty_id}/delete", response_class=RedirectResponse)
def delete_bounty(
    bounty_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """删除悬赏"""
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="悬赏不存在")
    
    # 检查权限
    if bounty.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限删除此悬赏")
    
    db.delete(bounty)
    db.commit()
    
    return RedirectResponse(url="/bounties", status_code=status.HTTP_303_SEE_OTHER)

