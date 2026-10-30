import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, database, auth
from app.config.templates import templates
from app.services.article_files import (
    article_static_dir_path,
    delete_article_static_dir,
    render_markdown,
    save_article_image,
    save_static_package,
    slugify,
)

router = APIRouter(tags=["Articles"])
logger = logging.getLogger(__name__)


@router.get("/articles", response_class=HTMLResponse)
def list_articles(request: Request, db: Session = Depends(database.get_db)):
    articles = (
        db.query(models.Article)
        .filter(models.Article.status == "published")
        .order_by(models.Article.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "articles_list.html", {"request": request, "articles": articles}
    )


@router.get("/article/{slug}", response_class=HTMLResponse)
def article_detail(slug: str, request: Request, db: Session = Depends(database.get_db)):
    article = (
        db.query(models.Article)
        .filter(models.Article.slug == slug, models.Article.status == "published")
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    # 纯静态模式：无正文，仅有静态包时直接跳转到静态入口
    if article.static_path and not (article.content_md and article.content_md.strip()):
        return RedirectResponse(url=f"/article/{article.slug}/static")
    return templates.TemplateResponse(
        "article_detail.html", {"request": request, "article": article}
    )


@router.get("/admin/articles/new", response_class=HTMLResponse)
def new_article_form(
    request: Request, admin_user: models.User = Depends(auth.get_current_admin_user)
):
    return templates.TemplateResponse(
        "article_form.html",
        {"request": request, "article": None, "action": "create"},
    )


@router.post("/admin/articles/new", response_class=HTMLResponse)
async def create_article(
    request: Request,
    title: str = Form(...),
    slug: Optional[str] = Form(None),
    content_md: Optional[str] = Form(""),
    static_path: Optional[str] = Form(None),
    static_package: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    slug_value = slugify(slug or title)
    if not slug_value:
        raise HTTPException(status_code=400, detail="标题无法生成有效的文章 slug")
    if db.query(models.Article).filter(models.Article.slug == slug_value).first():
        raise HTTPException(status_code=400, detail="slug 已存在，请更换")

    content_html = render_markdown(content_md or "")
    final_static_path = static_path
    if (not final_static_path) and static_package and static_package.filename:
        final_static_path = save_static_package(slug_value, static_package)

    article = models.Article(
        title=title,
        slug=slug_value,
        content_md=content_md or "",
        content_html=content_html,
        status="published",
        author_id=admin_user.id,
        static_path=final_static_path,
    )
    db.add(article)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="slug 已存在，请更换")
    return RedirectResponse(url=f"/article/{slug_value}", status_code=303)


@router.get("/admin/articles/{article_id}/edit", response_class=HTMLResponse)
def edit_article_form(
    article_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    return templates.TemplateResponse(
        "article_form.html",
        {"request": request, "article": article, "action": "edit"},
    )


@router.post("/admin/articles/{article_id}/edit", response_class=HTMLResponse)
async def update_article(
    article_id: int,
    request: Request,
    title: str = Form(...),
    content_md: Optional[str] = Form(""),
    static_path: Optional[str] = Form(None),
    static_package: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    article.title = title
    article.content_md = content_md or ""
    article.content_html = render_markdown(article.content_md)

    if static_path:
        article.static_path = static_path
    elif static_package and static_package.filename:
        article.static_path = save_static_package(article.slug, static_package)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="文章 slug 冲突，请重试")
    return RedirectResponse(url=f"/article/{article.slug}", status_code=303)


@router.post("/admin/articles/{article_id}/delete")
def delete_article(
    article_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    slug = article.slug
    db.delete(article)
    db.commit()
    try:
        delete_article_static_dir(slug)
    except Exception:
        logger.exception("删除文章静态目录失败: slug=%s", slug)
    return RedirectResponse(url="/articles", status_code=303)


@router.post("/admin/articles/preview")
async def preview_markdown(
    content_md: str = Form(""),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    html = render_markdown(content_md)
    return {"html": html}


@router.post("/admin/articles/upload_image")
async def upload_image(
    file: UploadFile = File(...),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    url = save_article_image(file)
    return JSONResponse({"url": url})


@router.post("/admin/articles/upload_static")
async def upload_static(
    slug: str = Form(...),
    static_package: UploadFile = File(...),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    slug_value = slugify(slug)
    if not slug_value:
        raise HTTPException(status_code=400, detail="无效的文章 slug")
    static_path = save_static_package(slug_value, static_package)
    return JSONResponse({"static_path": static_path})


@router.get("/article/{slug}/static")
def redirect_static(slug: str):
    """
    优先跳转到静态包中的 index.html / index.htm，找不到则跳到静态根路径。
    """
    base_path = article_static_dir_path(slug)
    index_html = base_path / "index.html"
    index_htm = base_path / "index.htm"
    if index_html.exists():
        return RedirectResponse(url=f"/static/articles/{slug}/index.html")
    if index_htm.exists():
        return RedirectResponse(url=f"/static/articles/{slug}/index.htm")
    return RedirectResponse(url=f"/static/articles/{slug}/")

