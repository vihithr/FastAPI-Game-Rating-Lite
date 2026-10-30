import logging
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config.constants import BASE_DIR

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 1 * 1024 * 1024
MAX_ARTICLE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 20_000_000
STATIC_ROOT = (BASE_DIR / "app" / "static").resolve()

COVER_THUMB_WIDTHS = (400, 800)
COVER_THUMB_QUALITY = 80
COVERS_URL_PREFIX = "/static/uploads/covers/"


class InvalidCoverImage(Exception):
    pass

# content-type -> (允许的后缀, 无后缀时的默认后缀)
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ({".jpg", ".jpeg"}, ".jpg"),
    "image/png": ({".png"}, ".png"),
    "image/gif": ({".gif"}, ".gif"),
    "image/webp": ({".webp"}, ".webp"),
}


def _matches_signature(contents: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return contents.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return contents.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/gif":
        return contents.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return (
            len(contents) >= 12
            and contents[:4] == b"RIFF"
            and contents[8:12] == b"WEBP"
        )
    return False


def validate_image_upload(
    upload: UploadFile,
    contents: bytes,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> str:
    """校验图片大小、类型、扩展名和文件签名，返回安全的保存后缀。"""
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"图片文件大小不能超过 {max_bytes // (1024 * 1024)}MB",
        )

    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="只支持上传 JPG, PNG, GIF, WebP 格式的图片",
        )

    allowed_suffixes, default_suffix = ALLOWED_IMAGE_TYPES[content_type]
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix:
        if suffix not in allowed_suffixes:
            raise HTTPException(
                status_code=400,
                detail="图片扩展名与文件类型不匹配",
            )
    else:
        suffix = default_suffix

    if not _matches_signature(contents, content_type):
        raise HTTPException(
            status_code=400,
            detail="图片内容与文件类型不匹配",
        )

    return suffix


def _cover_thumb_paths(source_path: Path) -> list[Path]:
    if "thumbs" in source_path.parts:
        return []
    return [
        source_path.parent / "thumbs" / str(width) / f"{source_path.stem}.webp"
        for width in COVER_THUMB_WIDTHS
    ]


def _load_cover_image(source_path: Path) -> Image.Image:
    try:
        with Image.open(source_path) as image:
            if image.width * image.height > MAX_COVER_PIXELS:
                raise InvalidCoverImage
            image.load()
            return ImageOps.exif_transpose(image).copy()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
    ) as exc:
        raise InvalidCoverImage from exc


def _write_webp(image: Image.Image, target_path: Path, width: int) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if image.mode not in ("RGB", "RGBA"):
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
    if image.width > width:
        height = max(1, round(image.height * width / image.width))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image.save(target_path, format="WEBP", quality=COVER_THUMB_QUALITY, method=4)
    target_path.chmod(0o644)


def generate_cover_derivatives(source_path: Path) -> list[Path]:
    targets = _cover_thumb_paths(source_path)
    image = _load_cover_image(source_path)
    try:
        for target_path, width in zip(targets, COVER_THUMB_WIDTHS):
            _write_webp(image, target_path, width)
    finally:
        image.close()
    return targets


def cover_thumbnail_url(url: Optional[str], width: int = 400) -> Optional[str]:
    if width not in COVER_THUMB_WIDTHS:
        width = COVER_THUMB_WIDTHS[0]
    if not url or not url.startswith(COVERS_URL_PREFIX):
        return url
    relative = url[len(COVERS_URL_PREFIX):]
    if relative.startswith("thumbs/"):
        return url
    return f"{COVERS_URL_PREFIX}thumbs/{width}/{Path(relative).stem}.webp"


def _delete_cover_files(source_path: Path) -> None:
    source_path.unlink(missing_ok=True)
    for path in _cover_thumb_paths(source_path):
        path.unlink(missing_ok=True)


def save_cover_image(upload: UploadFile, contents: bytes, upload_dir: Path) -> str:
    """保存游戏/资源封面，返回写入数据库的静态路径。"""
    suffix = validate_image_upload(upload, contents)
    upload_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    save_path = upload_dir / f"{token}{suffix}"
    save_path.write_bytes(contents)
    save_path.chmod(0o644)
    try:
        generate_cover_derivatives(save_path)
    except InvalidCoverImage:
        _delete_cover_files(save_path)
        raise HTTPException(status_code=400, detail="图片无法解析，请更换文件")
    except Exception:
        _delete_cover_files(save_path)
        logger.exception("生成封面缩略图失败")
        raise
    return f"/static/uploads/covers/{token}{suffix}"


def static_file_path(url: Optional[str]) -> Optional[Path]:
    """把 /static/... URL 安全地映射为 static 目录内的文件路径。"""
    if not url or not url.startswith("/static/"):
        return None
    relative = url[len("/static/"):]
    candidate = (STATIC_ROOT / relative).resolve()
    if candidate != STATIC_ROOT and STATIC_ROOT not in candidate.parents:
        return None
    return candidate


def delete_static_file(url: Optional[str]) -> None:
    path = static_file_path(url)
    if path is None or not path.is_file():
        return
    derivative_paths = (
        _cover_thumb_paths(path) if url and url.startswith(COVERS_URL_PREFIX) else []
    )
    path.unlink()
    for derivative_path in derivative_paths:
        derivative_path.unlink(missing_ok=True)
