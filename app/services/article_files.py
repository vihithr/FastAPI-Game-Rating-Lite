import io
import secrets
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.config.constants import BASE_DIR
from app.services.uploads import MAX_ARTICLE_IMAGE_BYTES, validate_image_upload

try:
    import markdown as md
except ImportError:  # pragma: no cover
    md = None

try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None

ARTICLES_ROOT = (BASE_DIR / "app" / "static" / "articles").resolve()
ARTICLE_UPLOADS_ROOT = (BASE_DIR / "app" / "static" / "uploads" / "articles").resolve()

MAX_STATIC_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_STATIC_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def render_markdown(content_md: str) -> str:
    if not content_md:
        return ""
    if md is None:
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
        html = bleach.clean(
            html, tags=allowed_tags, attributes=allowed_attrs, strip=True
        )
    return html


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def article_static_dir_path(slug: str) -> Path:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        raise HTTPException(status_code=400, detail="无效的文章 slug")
    target = (ARTICLES_ROOT / slug).resolve()
    if target != ARTICLES_ROOT and ARTICLES_ROOT not in target.parents:
        raise HTTPException(status_code=400, detail="无效的文章 slug")
    return target


def ensure_article_static_dir(slug: str) -> Path:
    target_dir = article_static_dir_path(slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def delete_article_static_dir(slug: str) -> None:
    target_dir = article_static_dir_path(slug)
    if target_dir.is_dir():
        shutil.rmtree(target_dir)


def save_static_package(slug: str, upload: Optional[UploadFile]) -> Optional[str]:
    if not upload or not upload.filename:
        return None
    if not upload.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持上传 zip 静态包")

    content = upload.file.read()
    if len(content) > MAX_STATIC_PACKAGE_BYTES:
        raise HTTPException(status_code=400, detail="静态包最大 50MB")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total_size = 0
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or any(part == ".." for part in parts):
                    raise HTTPException(status_code=400, detail="静态包包含非法路径")
                total_size += info.file_size
                if total_size > MAX_STATIC_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=400, detail="静态包解压后不能超过 200MB"
                    )

            target_dir = ensure_article_static_dir(slug)
            shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            archive.extractall(target_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="静态包不是有效的 zip 文件")

    return f"/static/articles/{slug}/"


def save_article_image(upload: UploadFile) -> str:
    content = upload.file.read()
    suffix = validate_image_upload(
        upload, content, max_bytes=MAX_ARTICLE_IMAGE_BYTES
    )
    ARTICLE_UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(upload.filename or "").stem) or "image"
    target_name = f"{stem}-{secrets.token_hex(4)}{suffix}"
    target_path = ARTICLE_UPLOADS_ROOT / target_name
    target_path.write_bytes(content)
    target_path.chmod(0o644)
    return f"/static/uploads/articles/{target_name}"
