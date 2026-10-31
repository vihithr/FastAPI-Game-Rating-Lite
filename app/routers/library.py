"""STG 资料库 —— 本机采集的 901 部射击游戏档案。

只读，独立于社区的 games 表：这里放的是「采集来的档案」，不参与评分。
数据源：app/data/library.json（由 stg_web/scripts/build_library.py 生成），
封面：app/static/library/covers/。
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import database, models
from app.config.constants import BASE_DIR
from app.config.templates import templates

router = APIRouter(tags=["Library"])
logger = logging.getLogger(__name__)

_DATA_PATH = Path(BASE_DIR) / "app" / "data" / "library.json"
_COVER_ROOT = Path(BASE_DIR) / "app" / "static" / "library" / "covers"
_records: list[dict[str, Any]] | None = None
_by_id: dict[str, dict[str, Any]] = {}
_by_norm: dict[str, dict[str, Any]] = {}

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

# 采集来源：rid 的前缀就是来源标识（如 shmups_wiki:1941-counter-attack）
SOURCE_META: dict[str, tuple[str, str]] = {
    "shmups_wiki": ("shmups.wiki", "https://shmups.wiki/"),
    "doujinstyle": ("DoujinStyle", "https://doujinstyle.com/"),
    "enwiki": ("英文维基百科", "https://en.wikipedia.org/"),
    "curated": ("手工整理", ""),
    "enrich": ("补充采集", ""),
    "steam": ("Steam 商店", "https://store.steampowered.com/"),
}

CJK_RE = re.compile(r"[\u3400-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
NON_ALNUM = re.compile(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+")


def norm(text: str | None) -> str:
    """用于跨表匹配的归一化：NFKC、小写、∀→v、去掉所有标点空白。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower().replace("∀", "v")
    return NON_ALNUM.sub("", s)


LATIN_RE = re.compile(r"[A-Za-z]")


def lang_of(text: str | None) -> str:
    """粗判简介语种。

    两个坑都要避开：
    1. 英文简介里夹日文原名（"1941: カウンターアタック is a vertically…"），
       只看「有没有假名」会误判成日文；
    2. 中文简介里夹英文专有名词（"Team Shanghai Alice 发布的同人射击作品"），
       只看「拉丁字母占比」会误判成英文——这类文本拉丁字母能占到七成。

    所以先看汉字/假名是否达到一定比例，再看拉丁字母。
    """
    if not text:
        return ""
    kana = len(KANA_RE.findall(text))
    cjk = len(CJK_RE.findall(text))
    latin = len(LATIN_RE.findall(text))
    total = kana + cjk + latin
    if not total:
        return ""
    cjkish = kana + cjk
    if cjkish >= 4 and cjkish / total >= 0.25:
        return "ja" if kana and kana / cjkish > 0.1 else "zh"
    if latin / total > 0.7:
        return "en"
    return "zh"


def source_of(rid: str) -> tuple[str, str, str]:
    """返回 (来源键, 展示名, 主页链接)。"""
    key = (rid or "").split(":")[0]
    label, url = SOURCE_META.get(key, (key or "未知", ""))
    return key, label, url


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
            key, label, url = source_of(rec.get("rid") or "")
            rec["src_key"] = key
            rec["src_label"] = label
            rec["src_url"] = url
            rec["lang"] = lang_of(rec.get("desc"))
            rec["platform_text"] = " / ".join(
                platform_label(p) for p in (rec.get("platforms") or [])
            )
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
        _by_norm.clear()
        for r in data:
            for name in (r.get("title"), r.get("zh"), r.get("orig")):
                n = norm(name)
                if n:
                    _by_norm.setdefault(n, r)
        logger.info("资料库已载入 %d 条记录", len(data))
    return _records


def all_records() -> list[dict[str, Any]]:
    """对外暴露只读记录列表（sitemap 等场景用）。"""
    return _load()


def find_entry_for_game(game: models.Game) -> dict[str, Any] | None:
    """评分库的作品 → 资料库条目（按标题/别名/译名归一化匹配）。"""
    _load()
    names = [game.title]
    names += [a.name for a in game.aliases]
    names += [t.name for t in game.translations]
    for name in names:
        rec = _by_norm.get(norm(name))
        if rec:
            return rec
    return None


def _find_game_id(db: Session, rec: dict[str, Any]) -> int | None:
    """资料库条目 → 评分库的作品 id（反向匹配）。"""
    names = [n.strip().lower() for n in (rec.get("title"), rec.get("zh"), rec.get("orig")) if n]
    if not names:
        return None
    game = (
        db.query(models.Game)
        .filter(func.lower(models.Game.title).in_(names))
        .first()
    )
    if game:
        return game.id
    game = (
        db.query(models.Game)
        .join(models.Alias, models.Alias.game_id == models.Game.id)
        .filter(func.lower(models.Alias.name).in_(names))
        .first()
    )
    if game:
        return game.id
    game = (
        db.query(models.Game)
        .join(models.Translation, models.Translation.game_id == models.Game.id)
        .filter(func.lower(models.Translation.name).in_(names))
        .first()
    )
    return game.id if game else None


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


def negotiate_lang(header: str | None, rec: dict[str, Any]) -> str:
    """按浏览器 Accept-Language 决定默认展示哪种简介。

    返回 "zh"（中文译文）或 "orig"（原文）。没有译文的条目一律 "orig"。

    中文用户看中文、英文/日文用户看原文，比让人每次手动点一下自然。
    没有 Accept-Language 头时退回中文——站点本身是中文站。
    """
    if not rec.get("zh_desc"):
        return "orig"
    if not header:
        return "zh"

    prefs: list[tuple[float, str]] = []
    for part in header.split(","):
        seg = part.split(";")
        tag = seg[0].strip().lower()
        if not tag:
            continue
        q = 1.0
        for s in seg[1:]:
            s = s.strip()
            if s.startswith("q="):
                try:
                    q = float(s[2:])
                except ValueError:
                    q = 0.0
        prefs.append((q, tag))
    prefs.sort(key=lambda x: -x[0])

    for _, tag in prefs:
        if tag.startswith("zh"):
            return "zh"
        if tag.startswith(("ja", "en")):
            return "orig"
    return "orig"


@router.get("/library/{slug}", response_class=HTMLResponse)
def library_detail(
    request: Request,
    slug: str,
    db: Session = Depends(database.get_db),
):
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
            "game_id": _find_game_id(db, rec),
            "default_lang": negotiate_lang(request.headers.get("accept-language"), rec),
            "related_series": related_series,
            "related_company": related_company,
            "platform_label": platform_label,
            "stats": _stats(records),
        },
    )
