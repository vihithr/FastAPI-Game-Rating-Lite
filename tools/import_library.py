#!/usr/bin/env python3
"""把采集来的 STG 档案（app/data/library.json）导入社区评分库。

- 按 title 去重：库里已有的作品不重复导入
- 封面走站内 uploads 流程：复制原图 + 生成 thumbs/400|800 的 webp 派生图，
  否则模板里的 cover_thumb() 会 404
- 标签/译名/别名按站内关系表落库
- 每条记录用 SAVEPOINT 包裹，单条失败不影响其余

用法（服务器上，用 venv 的 python）：
    venv/bin/python tools/import_library.py --dry-run
    venv/bin/python tools/import_library.py
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.uploads import (  # noqa: E402
    COVERS_URL_PREFIX,
    generate_cover_derivatives,
)

LIB_PATH = BASE_DIR / "app" / "data" / "library.json"
SRC_COVERS = BASE_DIR / "app" / "static" / "library" / "covers"
DST_COVERS = BASE_DIR / "app" / "static" / "uploads" / "covers"
DEFAULT_OWNER = 1
PLACEHOLDER_COMPANY = "未知"


def attach_cover(filename: str) -> str | None:
    """把采集来的封面落到站内 covers 目录并生成缩略图，返回 image_url。"""
    if not filename:
        return None
    src = SRC_COVERS / filename
    if not src.is_file():
        return None
    suffix = src.suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return None
    token = secrets.token_hex(16)
    DST_COVERS.mkdir(parents=True, exist_ok=True)
    dst = DST_COVERS / f"{token}{suffix}"
    dst.write_bytes(src.read_bytes())
    dst.chmod(0o644)
    try:
        generate_cover_derivatives(dst)
    except Exception as exc:  # 坏图就放弃封面，但作品照常导入
        dst.unlink(missing_ok=True)
        print(f"  ! 封面处理失败 {filename}: {exc}", file=sys.stderr)
        return None
    return f"{COVERS_URL_PREFIX}{token}{suffix}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    ap.add_argument("--owner", type=int, default=DEFAULT_OWNER, help="created_by 用户 ID")
    ap.add_argument("--limit", type=int, default=0, help="只导入前 N 条（调试用）")
    args = ap.parse_args()

    records = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]

    db = SessionLocal()
    try:
        owner = db.get(models.User, args.owner)
        if owner is None:
            sys.exit(f"找不到用户 id={args.owner}，无法确定 created_by")

        existing_titles = {t.lower() for (t,) in db.query(models.Game.title).all()}
        tag_cache = {t.name: t for t in db.query(models.Tag).all()}

        added = skipped = no_cover = failed = 0
        added_titles: list[str] = []

        for rec in records:
            title = (rec.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            if title.lower() in existing_titles:
                skipped += 1
                continue

            if args.dry_run:
                added += 1
                if not rec.get("cover"):
                    no_cover += 1
                continue

            nested = db.begin_nested()
            try:
                image_url = attach_cover(rec.get("cover") or "")
                if not image_url:
                    no_cover += 1

                game = models.Game(
                    title=title,
                    company=(rec.get("company") or "").strip() or PLACEHOLDER_COMPANY,
                    description=(rec.get("desc") or "").strip() or None,
                    image_url=image_url,
                    created_by=owner.id,
                )

                for name in rec.get("tags") or []:
                    name = (name or "").strip()
                    if not name:
                        continue
                    tag = tag_cache.get(name)
                    if tag is None:
                        tag = models.Tag(name=name)
                        db.add(tag)
                        db.flush()
                        tag_cache[name] = tag
                    if tag not in game.tags:
                        game.tags.append(tag)

                zh = (rec.get("zh") or "").strip()
                if zh and zh.lower() != title.lower():
                    game.translations.append(models.Translation(name=zh))

                orig = (rec.get("orig") or "").strip()
                if orig and orig.lower() != title.lower():
                    game.aliases.append(models.Alias(name=orig))

                db.add(game)
                db.flush()
                nested.commit()

                existing_titles.add(title.lower())
                added += 1
                added_titles.append(title)
            except Exception as exc:
                nested.rollback()
                failed += 1
                print(f"  ! 导入失败 {title}: {exc}", file=sys.stderr)

            if added and added % 100 == 0:
                db.commit()
                print(f"  …已导入 {added}")

        if not args.dry_run:
            db.commit()

        total = db.query(models.Game).count()
        print("\n===== 导入结果 =====")
        print(f"数据源记录      : {len(records)}")
        print(f"新导入          : {added}")
        print(f"跳过（已存在）  : {skipped}")
        print(f"其中无封面      : {no_cover}")
        print(f"失败            : {failed}")
        print(f"库内作品总数    : {total}")
        if added_titles[:5]:
            print("样例            :", "、".join(added_titles[:5]))
        if args.dry_run:
            print("\n[dry-run] 未写入数据库")
    finally:
        db.close()


if __name__ == "__main__":
    main()
