#!/usr/bin/env python3
"""把采集档案里的 platform / release_year / series 回填到 games 表。

匹配顺序：标题 → 别名 → 译名，全部走归一化（NFKC、小写、去非字母数字），
所以「怒首领蜂」能对上档案里的 DoDonPachi（若档案带中文译名）。

用法：
    venv/bin/python tools/backfill_meta.py --dry-run
    venv/bin/python tools/backfill_meta.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

LIB_PATH = BASE_DIR / "app" / "data" / "library.json"

PLATFORM_LABELS = {
    "pc": "PC", "arcade": "街机", "switch": "Switch", "ps1": "PS1", "ps2": "PS2",
    "ps3": "PS3", "ps4": "PS4", "ps5": "PS5", "psp": "PSP", "vita": "PSV",
    "saturn": "Saturn", "dreamcast": "DC", "md": "MD", "nes": "FC/NES", "snes": "SFC",
    "n64": "N64", "gamecube": "NGC", "wii": "Wii", "gba": "GBA", "gb": "GB",
    "pce": "PCE", "msx": "MSX", "wonderswan": "WS", "xbox": "Xbox",
    "xbox360": "X360", "xboxone": "XOne", "mobile": "手机", "dos": "DOS",
    "web": "Web", "linux": "Linux", "mac": "Mac", "x68000": "X68000",
    "amiga": "Amiga", "c64": "C64", "3ds": "3DS", "nds": "NDS", "other": "其他",
}

NON_ALNUM = re.compile(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+")


def norm(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    s = s.replace("∀", "v")
    return NON_ALNUM.sub("", s)


def platform_text(keys: list[str]) -> str:
    labels: list[str] = []
    for k in keys or []:
        label = PLATFORM_LABELS.get(k, k.upper() if len(k) <= 4 else k.title())
        if label not in labels:
            labels.append(label)
    return " / ".join(labels)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    index: dict[str, dict] = {}
    for rec in records:
        for key in (rec.get("title"), rec.get("zh"), rec.get("orig")):
            n = norm(key)
            if n:
                index.setdefault(n, rec)

    db = SessionLocal()
    try:
        games = db.query(models.Game).all()
        hit = miss = 0
        for g in games:
            names = [g.title] + [a.name for a in g.aliases] + [t.name for t in g.translations]
            rec = None
            for name in names:
                rec = index.get(norm(name))
                if rec:
                    break
            if not rec:
                miss += 1
                continue

            platform = platform_text(rec.get("platforms") or [])
            year = rec.get("year") or None
            series = (rec.get("series") or "").strip() or None

            if args.dry_run:
                hit += 1
                continue

            changed = False
            if platform and g.platform != platform:
                g.platform = platform
                changed = True
            if year and g.release_year != year:
                g.release_year = year
                changed = True
            if series and g.series != series:
                g.series = series
                changed = True
            if changed:
                hit += 1
            else:
                miss += 1

        if not args.dry_run:
            db.commit()

        print(f"作品总数 {len(games)}｜匹配并写入 {hit}｜未匹配 {miss}")
        if args.dry_run:
            print("[dry-run] 未写入")
        else:
            with_platform = db.query(models.Game).filter(models.Game.platform.isnot(None)).count()
            with_year = db.query(models.Game).filter(models.Game.release_year.isnot(None)).count()
            with_series = db.query(models.Game).filter(models.Game.series.isnot(None)).count()
            print(f"有平台 {with_platform}｜有年份 {with_year}｜有系列 {with_series}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
