#!/usr/bin/env python3
"""给资料库封面生成 webp 缩略图。

/library 列表页的卡片只有 150~270px 宽，却直接加载原图（平均 40KB，
大的到 190KB），第 1 页 45 张就是 1.9MB。这里按最长边 400px 生成 webp，
列表页改用缩略图，详情页仍用原图。

用法：
    venv/bin/python tools/build_library_thumbs.py --dry-run
    venv/bin/python tools/build_library_thumbs.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent.parent
COVERS = BASE_DIR / "app" / "static" / "library" / "covers"
THUMBS = COVERS / "thumbs"

MAX_SIDE = 400
QUALITY = 78
SRC_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def build_one(src: Path, dst: Path) -> tuple[int, int]:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        before = src.stat().st_size
        # 只缩不放：原图本来就小于 400px 的话，转 webp 也能压一轮
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "WEBP", quality=QUALITY, method=6)
        return before, dst.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="已存在也重建")
    args = ap.parse_args()

    if not COVERS.is_dir():
        sys.exit(f"封面目录不存在: {COVERS}")

    sources = sorted(
        f for f in COVERS.iterdir() if f.is_file() and f.suffix.lower() in SRC_SUFFIXES
    )
    print(f"源封面 {len(sources)} 张")

    done = skipped = failed = 0
    total_before = total_after = 0

    for src in sources:
        dst = THUMBS / f"{src.stem}.webp"
        if dst.exists() and not args.force and dst.stat().st_mtime >= src.stat().st_mtime:
            skipped += 1
            total_before += src.stat().st_size
            total_after += dst.stat().st_size
            continue
        if args.dry_run:
            done += 1
            total_before += src.stat().st_size
            continue
        try:
            before, after = build_one(src, dst)
            total_before += before
            total_after += after
            done += 1
        except Exception as exc:
            failed += 1
            print(f"  ! {src.name}: {exc}", file=sys.stderr)

        if done and done % 150 == 0:
            print(f"  …已生成 {done}")

    print(f"\n生成 {done}｜跳过 {skipped}｜失败 {failed}")
    if not args.dry_run and total_after:
        print(
            f"体积 {total_before/1048576:.1f} MB → {total_after/1048576:.1f} MB "
            f"（省 {(1 - total_after/total_before) * 100:.0f}%）"
        )
    if args.dry_run:
        print("[dry-run] 未写入")


if __name__ == "__main__":
    main()
