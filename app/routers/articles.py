import os
import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app import models, database, auth
from app.config.templates import templates
from app.config.constants import BASE_DIR

try:
    import markdown as md
except ImportError:  # pragma: no cover
    md = None

try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None

router = APIRouter(tags=["Articles"])


def render_markdown(content_md: str) -> str:
    if not content_md:
        return ""
    if md is None:
        # 最简 fallback，直接转义换行
        return content_md.replace("\n", "<br>")
    html = md.markdown(content_md, extensions=["fenced_code", "tables"])
    if bleach:
        allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
            "p",
            "pre",
            "code",
            "h1",
            "h2",
            "h3",
            "h4",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "img",
            "figure",
            "figcaption",
        ]
        allowed_attrs = {
            "*": ["class", "id", "style"],
            "a": ["href", "title", "target", "rel"],
            "img": ["src", "alt", "title", "width", "height", "loading", "referrerpolicy"],
        }
        html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return html


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def ensure_article_static_dir(slug: str) -> Path:
    target_dir = BASE_DIR / "app" / "static" / "articles" / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def ensure_article_upload_dir() -> Path:
    target_dir = BASE_DIR / "app" / "static" / "uploads" / "articles"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def handle_static_upload(slug: str, upload: Optional[UploadFile]) -> Optional[str]:
    if not upload or not upload.filename:
        return None
    filename = upload.filename.lower()
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持上传 zip 静态包")

    content = upload.file.read()
    max_size = 50 * 1024 * 1024  # 50MB
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="静态包最大 50MB")

    target_dir = ensure_article_static_dir(slug)

    # 清空旧文件
    for item in target_dir.iterdir():
        if item.is_file():
            item.unlink()
        else:
            # 简单递归删除目录
            for root, dirs, files in os.walk(item, topdown=False):
                for f in files:
                    Path(root, f).unlink()
                for d in dirs:
                    Path(root, d).rmdir()
            item.rmdir()

    # 直接从内存解压
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        zf.extractall(target_dir)

    # 返回静态路径
    return f"/static/articles/{slug}/"


def handle_image_upload(upload: UploadFile) -> str:
    filename = upload.filename.lower()
    allowed_ext = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
    if not any(filename.endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=400, detail="仅支持图片上传")
    content = upload.file.read()
    max_size = 10 * 1024 * 1024  # 10MB
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="图片最大 10MB")

    upload_dir = ensure_article_upload_dir()
    target_name = f"{slugify(Path(filename).stem)}-{os.urandom(4).hex()}{Path(filename).suffix}"
    target_path = upload_dir / target_name
    with open(target_path, "wb") as f:
        f.write(content)
    # 返回可访问 URL
    rel = target_path.relative_to(BASE_DIR / "app")
    return "/" + rel.as_posix()


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
    if db.query(models.Article).filter(models.Article.slug == slug_value).first():
        raise HTTPException(status_code=400, detail="slug 已存在，请更换")

    content_html = render_markdown(content_md or "")
    final_static_path = static_path
    if (not final_static_path) and static_package and static_package.filename:
        final_static_path = handle_static_upload(slug_value, static_package)

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
    db.commit()
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
        article.static_path = handle_static_upload(article.slug, static_package)

    db.commit()
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
    db.delete(article)
    db.commit()
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
    url = handle_image_upload(file)
    return JSONResponse({"url": url})


@router.post("/admin/articles/upload_static")
async def upload_static(
    slug: str = Form(...),
    static_package: UploadFile = File(...),
    admin_user: models.User = Depends(auth.get_current_admin_user),
):
    static_path = handle_static_upload(slugify(slug), static_package)
    return JSONResponse({"static_path": static_path})


@router.get("/article/{slug}/static")
def redirect_static(slug: str):
    """
    优先跳转到静态包中的 index.html / index.htm，找不到则跳到静态根路径。
    """
    base_path = BASE_DIR / "app" / "static" / "articles" / slug
    index_html = base_path / "index.html"
    index_htm = base_path / "index.htm"
    if index_html.exists():
        return RedirectResponse(url=f"/static/articles/{slug}/index.html")
    if index_htm.exists():
        return RedirectResponse(url=f"/static/articles/{slug}/index.htm")
    return RedirectResponse(url=f"/static/articles/{slug}/")

