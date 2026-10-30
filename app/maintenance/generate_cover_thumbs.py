from pathlib import Path

from app.config.constants import BASE_DIR
from app.services.uploads import COVER_THUMB_WIDTHS, generate_cover_derivatives


def generate_all_cover_thumbs() -> None:
    covers_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
    if not covers_dir.exists():
        print("[covers] 目录不存在，跳过")
        return

    sources = [p for p in covers_dir.iterdir() if p.is_file()]
    original_bytes = sum(p.stat().st_size for p in sources)
    for source in sources:
        generate_cover_derivatives(source)

    thumb_files = list((covers_dir / "thumbs").glob("*/*.webp"))
    thumb_bytes = sum(p.stat().st_size for p in thumb_files)
    widths = ", ".join(str(w) for w in COVER_THUMB_WIDTHS)
    print(
        f"[covers] 生成 {len(sources)} 组缩略图（{widths}w），"
        f"原图 {original_bytes / 1024 / 1024:.1f} MB，"
        f"缩略图 {thumb_bytes / 1024 / 1024:.1f} MB"
    )


if __name__ == "__main__":
    generate_all_cover_thumbs()
