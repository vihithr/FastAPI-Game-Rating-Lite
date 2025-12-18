from fastapi import APIRouter, Depends, HTTPException, Request, Form, status, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_
from typing import Optional
from pathlib import Path
import secrets

from app import models, database, auth
from app.config.templates import templates
from app.config.constants import BASE_DIR


router = APIRouter(
    prefix="/resources",
    tags=["Resources"],
)


# --- 辅助函数 ---

def process_resource_tags(db: Session, resource: models.Resource, tags_str: str) -> None:
    """
    处理资源标签字符串，更新资源与 ResourceTag 的多对多关系。
    - 输入格式示例：\"东方, MAME 录屏  , stg\"（逗号或空白分隔）
    """
    resource.tags.clear()
    if not tags_str:
        return

    # 支持逗号和空白分隔符
    raw_parts = tags_str.replace("，", ",").split(",")
    tag_names = set()
    for part in raw_parts:
        for piece in part.split():
            name = piece.strip()
            if name:
                tag_names.add(name)

    if not tag_names:
        return

    existing_tags = db.query(models.ResourceTag).filter(models.ResourceTag.name.in_(tag_names)).all()
    existing_map = {t.name: t for t in existing_tags}

    for name in tag_names:
        tag = existing_map.get(name)
        if not tag:
            tag = models.ResourceTag(name=name)
            db.add(tag)
            db.flush()
        resource.tags.append(tag)


def save_resource_cover(image_file: UploadFile) -> Optional[str]:
    """
    保存资源封面图到静态目录，返回存入数据库的相对路径。
    限制：<1MB，JPG/PNG/WEBP/GIF
    """
    if not image_file or not image_file.filename:
        return None

    contents = image_file.file.read()
    file_size = len(contents)
    if file_size > 1 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片文件大小不能超过 1MB")

    if image_file.content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
        raise HTTPException(status_code=400, detail="只支持上传 JPG, PNG, GIF, WebP 格式的图片")

    upload_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
    upload_dir.mkdir(parents=True, exist_ok=True)

    token = secrets.token_hex(16)
    file_extension = Path(image_file.filename).suffix
    if not file_extension:
        content_type_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        file_extension = content_type_map.get(image_file.content_type, ".jpg")

    save_path = upload_dir / f"{token}{file_extension}"
    with open(save_path, "wb") as buffer:
        buffer.write(contents)

    return f"/static/uploads/covers/{token}{file_extension}"


# --- 页面路由 ---

@router.get("/", response_class=HTMLResponse)
def resource_list(
    request: Request,
    db: Session = Depends(database.get_db),
    page: int = 1,
    per_page: int = 20,
    q: Optional[str] = None,
    tag: Optional[str] = None,
):
    """
    资源列表页：
    - 紧凑列表布局
    - 支持关键词搜索（title + 标签）
    - 支持按单个标签过滤
    """
    page = max(1, page)
    per_page = max(1, min(50, per_page))

    query = db.query(models.Resource).options(
        selectinload(models.Resource.tags),
        selectinload(models.Resource.uploader),
    )

    # 仅展示有效资源；失效资源仍可通过详情访问
    query = query.filter(models.Resource.status == "valid")

    if q:
        pattern = f"%{q.strip()}%"
        # 标题或标签名匹配
        query = query.join(models.Resource.tags, isouter=True).filter(
            or_(
                models.Resource.title.ilike(pattern),
                models.ResourceTag.name.ilike(pattern),
            )
        )

    if tag:
        query = query.join(models.Resource.tags).filter(models.ResourceTag.name == tag)

    total_count = query.distinct().count()
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    resources = (
        query.order_by(models.Resource.heat.desc(), models.Resource.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # 热门标签（仅资源标签）
    tag_counts = (
        db.query(models.ResourceTag, func.count(models.resource_tag_association.c.resource_id).label("res_count"))
        .outerjoin(
            models.resource_tag_association,
            models.ResourceTag.id == models.resource_tag_association.c.resource_tag_id,
        )
        .group_by(models.ResourceTag.id)
        .having(func.count(models.resource_tag_association.c.resource_id) > 0)
        .order_by(func.count(models.resource_tag_association.c.resource_id).desc(), models.ResourceTag.name)
        .limit(30)
        .all()
    )
    popular_tags = [{"tag": t, "count": c} for t, c in tag_counts]

    # 推荐分类枚举（前端展示用，但数据库不强制）
    suggested_categories = ["游戏本体", "补丁", "OST", "DLC", "工具", "攻略/文档", "其他"]

    return templates.TemplateResponse(
        "resources_list.html",
        {
            "request": request,
            "resources": resources,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_count": total_count,
            "q": q or "",
            "active_tag": tag,
            "popular_tags": popular_tags,
            "suggested_categories": suggested_categories,
        },
    )


@router.get("/submit", response_class=HTMLResponse)
async def resource_submit_page(
    request: Request, current_user: models.User = Depends(auth.get_current_user)
):
    """资源提交页（仅登录用户可访问）"""
    suggested_categories = ["游戏本体", "补丁", "OST", "DLC", "工具", "攻略/文档", "其他"]
    return templates.TemplateResponse(
        "resource_submit.html",
        {
            "request": request,
            "suggested_categories": suggested_categories,
        },
    )


@router.post("/submit", response_class=RedirectResponse)
async def resource_submit(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
    title: str = Form(...),
    category: str = Form(...),
    tags: str = Form(...),
    content: str = Form(...),
    intro: str = Form(""),
    cover: UploadFile = File(None),
):
    """处理资源提交表单（仅登录用户）"""
    if not title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not category.strip():
        raise HTTPException(status_code=400, detail="分类不能为空")
    if not tags.strip():
        raise HTTPException(status_code=400, detail="标签不能为空")
    if not content.strip():
        raise HTTPException(status_code=400, detail="提交内容不能为空")

    cover_path = None
    if cover and cover.filename:
        cover_path = save_resource_cover(cover)

    new_resource = models.Resource(
        title=title.strip(),
        category=category.strip(),
        content=content.strip(),
        intro=intro.strip() or None,
        cover_image=cover_path,
        uploader_id=current_user.id,
    )

    try:
        process_resource_tags(db, new_resource, tags)
        db.add(new_resource)
        db.commit()
        db.refresh(new_resource)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建资源失败: {e}")

    return RedirectResponse(
        url=f"/resources/{new_resource.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{resource_id}", response_class=HTMLResponse)
def resource_detail(
    request: Request,
    resource_id: int,
    db: Session = Depends(database.get_db),
):
    """资源详情页"""
    resource = (
        db.query(models.Resource)
        .options(
            selectinload(models.Resource.tags),
            selectinload(models.Resource.uploader),
        )
        .filter(models.Resource.id == resource_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # 当前用户对该资源的投票（如果已登录）
    current_vote_value = 0
    if request.state.user:
        vote = (
            db.query(models.ResourceVote)
            .filter(
                models.ResourceVote.resource_id == resource.id,
                models.ResourceVote.user_id == request.state.user.id,
            )
            .first()
        )
        if vote:
            current_vote_value = vote.value

    return templates.TemplateResponse(
        "resource_detail.html",
        {
            "request": request,
            "resource": resource,
            "current_vote_value": current_vote_value,
        },
    )


@router.post("/{resource_id}/vote")
async def resource_vote(
    resource_id: int,
    direction: str = Form(...),  # "up" 或 "down"
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    资源投票：
    - 每人每资源最多一条记录
    - 重复同向投票为 no-op
    - 反向投票会修改 value 并调整 heat
    """
    resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="非法的投票方向")

    vote_value = 1 if direction == "up" else -1

    vote = (
        db.query(models.ResourceVote)
        .filter(
            models.ResourceVote.resource_id == resource_id,
            models.ResourceVote.user_id == current_user.id,
        )
        .first()
    )

    if vote is None:
        # 新投票
        vote = models.ResourceVote(
            resource_id=resource_id,
            user_id=current_user.id,
            value=vote_value,
        )
        resource.heat += vote_value
        db.add(vote)
    else:
        # 已经投过票
        if vote.value == vote_value:
            # 同向重复投票，不再变更
            return JSONResponse(
                {
                    "status": "ok",
                    "heat": resource.heat,
                    "vote": vote.value,
                    "message": "already_voted",
                }
            )
        # 反向修改：总热度需要调整 2
        delta = vote_value - vote.value
        resource.heat += delta
        vote.value = vote_value

    db.commit()
    db.refresh(resource)

    return JSONResponse(
        {
            "status": "ok",
            "heat": resource.heat,
            "vote": vote_value,
        }
    )


@router.post("/{resource_id}/delete", response_class=RedirectResponse)
async def resource_delete(
    resource_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    删除资源（仅上传者或管理员可以操作）。
    这里做物理删除；如果你更偏好逻辑删除，可以改为 status = 'invalid'。
    """
    resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    is_owner = resource.uploader_id == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限删除该资源")

    db.delete(resource)
    db.commit()

    return RedirectResponse(url="/resources", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{resource_id}/edit", response_class=HTMLResponse)
async def resource_edit_page(
    request: Request,
    resource_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """编辑资源页面（仅上传者或管理员）"""
    resource = (
        db.query(models.Resource)
        .options(selectinload(models.Resource.tags))
        .filter(models.Resource.id == resource_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    is_owner = resource.uploader_id == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限编辑该资源")

    # 将标签列表转成文本，默认用空格分隔
    tags_str = " ".join([t.name for t in resource.tags])
    suggested_categories = ["游戏本体", "补丁", "OST", "DLC", "工具", "攻略/文档", "其他"]

    return templates.TemplateResponse(
        "resource_submit.html",
        {
            "request": request,
            "resource": resource,
            "tags_str": tags_str,
            "suggested_categories": suggested_categories,
            "is_edit": True,
        },
    )


@router.post("/{resource_id}/edit", response_class=RedirectResponse)
async def resource_edit(
    resource_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
    title: str = Form(...),
    category: str = Form(...),
    tags: str = Form(...),
    content: str = Form(...),
    intro: str = Form(""),
    cover: UploadFile = File(None),
):
    """处理资源编辑提交（仅上传者或管理员）"""
    resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    is_owner = resource.uploader_id == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限编辑该资源")

    if not title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not category.strip():
        raise HTTPException(status_code=400, detail="分类不能为空")
    if not tags.strip():
        raise HTTPException(status_code=400, detail="标签不能为空")
    if not content.strip():
        raise HTTPException(status_code=400, detail="提交内容不能为空")

    resource.title = title.strip()
    resource.category = category.strip()
    resource.content = content.strip()
    resource.intro = intro.strip() or None

    # 可选更新封面
    if cover and cover.filename:
        new_cover = save_resource_cover(cover)
        resource.cover_image = new_cover

    process_resource_tags(db, resource, tags)
    db.commit()

    return RedirectResponse(
        url=f"/resources/{resource.id}", status_code=status.HTTP_303_SEE_OTHER
    )


