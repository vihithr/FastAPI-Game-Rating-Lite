"""STG 资料库 —— 本机采集的 901 部射击游戏档案。

只读，独立于社区的 games 表：这里放的是「采集来的档案」，不参与评分。
数据源：app/data/library.json（由 stg_web/scripts/build_library.py 生成），
封面：app/static/library/covers/。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.config.constants import BASE_DIR
from app.config.templates import templates

router = APIRouter(tags=["Library"])
logger = logging.getLogger(__name__)

_DATA_PATH = Path(BASE_DIR) / "app" / "data" / "library.json"
_COVER_ROOT = Path(BASE_DIR) / "app" / "static" / "library" / "covers"
_records: list[dict[str, Any]] | None = None
_by_id: dict[str, dict[str, Any]] = {}

PLATFORM_LABELS = {
    "pc": "PC",
    "arcade": "街机",
    "switch": "Switch",
    "ps1": "PS1",
    "ps2": "PS2",
    "ps3": "PS3",
    "ps4": "PS4",
    "ps5": "PS5",
    "psp": "PSP",
    "vita": "PSV",
    "saturn": "Saturn",
    "dreamcast": "DC",
    "md": "MD",
    "nes": "FC/NES",
    "snes": "SFC",
    "n64": "N64",
    "gamecube": "NGC",
    "wii": "Wii",
    "gba": "GBA",
    "gb": "GB",
    "pce": "PCE",
    "msx": "MSX",
    "wonderswan": "WS",
    "xbox": "Xbox",
    "xbox360": "X360",
    "xboxone": "XOne",
    "mobile": "手机",
    "dos": "DOS",
    "web": "Web",
    "linux": "Linux",
    "mac": "Mac",
    "x68000": "X68000",
    "amiga": "Amiga",
    "c64": "C64",
    "fm7": "FM-7",
    "pc88": "PC-88",
    "pc98": "PC-98",
    "3ds": "3DS",
    "nds": "NDS",
    "other": "其他",
    "unknown": "未标注",
}

SORTS = {
    "title": "按名称",
    "year": "按年份（早→晚）",
    "year-desc": "按年份（晚→早）",
    "company": "按开发商",
}


def platform_label(key: str) -> str:
    return PLATFORM_LABELS.get(key, key.upper() if len(key) <= 4 else key.title())


def subtitle(rec: dict[str, Any]) -> str:
    """卡片副标题：有中文名时显示英文原名，否则显示原文名——但不要和主标题重复。"""
    zh = (rec.get("zh") or "").strip()
    title = (rec.get("title") or "").strip()
    orig = (rec.get("orig") or "").strip()
    if zh:
        return title if title.lower() != zh.lower() else ""
    if orig and orig.lower() != title.lower():
        return orig
    return ""


def _load() -> list[dict[str, Any]]:
    """惰性加载一次，进程内常驻。"""
    global _records
    if _records is None:
        try:
            with _DATA_PATH.open(encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            logger.exception("资料库数据读取失败: %s", _DATA_PATH)
            data = []
        for rec in data:
            # 搜索用的扁平化干草堆，避免每次请求重复拼接
            rec["_hay"] = " ".join(
                str(rec.get(k) or "")
                for k in ("title", "zh", "orig", "company", "publisher", "series", "year")
            ).lower() + " " + " ".join(rec.get("tags") or []).lower() + " " + " ".join(
                rec.get("platforms") or []
            ).lower()
            rec["wide"] = bool(rec.get("cw") and rec.get("cw") > rec.get("ch"))
            rec["sub"] = subtitle(rec)
            # 列表页用 400px webp 缩略图，详情页才用原图
            cover = rec.get("cover") or ""
            if cover:
                thumb = f"thumbs/{Path(cover).stem}.webp"
                rec["thumb"] = (
                    thumb if (_COVER_ROOT / thumb).is_file() else cover
                )
            else:
                rec["thumb"] = ""
        _records = data
        _by_id.clear()
        _by_id.update({r["id"]: r for r in data})
        logger.info("资料库已载入 %d 条记录", len(data))
    return _records


def _facets(records: list[dict[str, Any]]) -> dict[str, Any]:
    platforms: dict[str, int] = {}
    tags: dict[str, int] = {}
    decades: dict[int, int] = {}
    for r in records:
        for p in r.get("platforms") or []:
            platforms[p] = platforms.get(p, 0) + 1
        for t in r.get("tags") or []:
            tags[t] = tags.get(t, 0) + 1
        y = r.get("year") or 0
        if y:
            decades[y // 10 * 10] = decades.get(y // 10 * 10, 0) + 1
    return {
        "platforms": sorted(platforms.items(), key=lambda kv: (-kv[1], kv[0])),
        "tags": sorted(tags.items(), key=lambda kv: (-kv[1], kv[0])),
        "decades": sorted(decades.items()),
    }


def _stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(records),
        "covers": sum(1 for r in records if r.get("cover")),
        "desc": sum(1 for r in records if r.get("desc")),
        "year": sum(1 for r in records if r.get("year")),
        "steam": sum(1 for r in records if r.get("steam")),
        "series": sum(1 for r in records if r.get("series")),
        "earliest": min((r["year"] for r in records if r.get("year")), default=0),
        "latest": max((r["year"] for r in records if r.get("year")), default=0),
    }


@router.get("/library", response_class=HTMLResponse)
def library_index(
    request: Request,
    q: str = "",
    platform: str = "",
    tag: str = "",
    decade: str = "",
    sort: str = "title",
    page: int = 1,
    per_page: int = 48,
):
    records = _load()
    q = (q or "").strip()
    sort = sort if sort in SORTS else "title"
    per_page = max(12, min(96, per_page))
    page = max(1, page)

    result = records
    if platform:
        result = [r for r in result if platform in (r.get("platforms") or [])]
    if tag:
        result = [r for r in result if tag in (r.get("tags") or [])]
    if decade.isdigit():
        low = int(decade)
        result = [r for r in result if r.get("year") and low <= r["year"] < low + 10]
    if q:
        words = [w for w in q.lower().split() if w]
        result = [r for r in result if all(w in r["_hay"] for w in words)]

    if sort == "year":
        result = sorted(result, key=lambda r: (r.get("year") or 9999, r["title"].lower()))
    elif sort == "year-desc":
        result = sorted(result, key=lambda r: (-(r.get("year") or 0), r["title"].lower()))
    elif sort == "company":
        result = sorted(result, key=lambda r: ((r.get("company") or "zzz").lower(), r["title"].lower()))
    else:
        result = sorted(result, key=lambda r: (r["title"].lower(), r.get("year") or 0))

    total_count = len(result)
    total_pages = (total_count + per_page - 1) // per_page if total_count else 1
    page = min(page, total_pages)
    start = (page - 1) * per_page
    items = result[start : start + per_page]

    facets = _facets(records)

    return templates.TemplateResponse(
        "library_list.html",
        {
            "request": request,
            "items": items,
            "stats": _stats(records),
            "total_count": total_count,
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "q": q,
            "active_platform": platform,
            "active_tag": tag,
            "active_decade": decade,
            "sort": sort,
            "sorts": SORTS,
            "platforms": facets["platforms"][:16],
            "tags": facets["tags"][:24],
            "decades": facets["decades"],
            "platform_label": platform_label,
        },
    )


@router.get("/library/{slug}", response_class=HTMLResponse)
def library_detail(request: Request, slug: str):
    records = _load()
    rec = _by_id.get(slug)
    if not rec:
        raise HTTPException(status_code=404, detail="资料库中找不到该作品")

    # 同系列 / 同开发商的作品，各取几条做关联
    related_series = [
        r
        for r in records
        if rec.get("series") and r.get("series") == rec.get("series") and r["id"] != rec["id"]
    ][:6]
    related_company = [
        r
        for r in records
        if rec.get("company")
        and r.get("company") == rec.get("company")
        and r["id"] != rec["id"]
        and not (rec.get("series") and r.get("series") == rec.get("series"))
    ][:6]

    return templates.TemplateResponse(
        "library_detail.html",
        {
            "request": request,
            "item": rec,
            "related_series": related_series,
            "related_company": related_company,
            "platform_label": platform_label,
            "stats": _stats(records),
        },
    )
