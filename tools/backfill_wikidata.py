#!/usr/bin/env python3
"""用 Wikidata 补全缺失的发行年份与平台。

只填 NULL 字段，不动已有数据。

匹配策略（关键是别选到消歧义页）：
1. 用标题 / 别名 / 译名分别去 wbsearchentities 搜，收集相似度 >= 0.85 的候选
2. 把所有候选 Q-id 批量拉一次实体（每请求 50 个）
3. 在相似度 >= 0.92 的候选里，**优先选真有 P577（发行日期）或 P400（平台）声明的**，
   否则会命中同名的消歧义条目——"Darius" 搜出来第一个就是无 claims 的消歧义页

用法：
    venv/bin/python tools/backfill_wikidata.py --dry-run
    venv/bin/python tools/backfill_wikidata.py --limit 50
    venv/bin/python tools/backfill_wikidata.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.routers.library import PLATFORM_LABELS  # noqa: E402

CACHE_PATH = BASE_DIR / "app" / "data" / "wikidata_cache.json"
UA = "STG-Ratings-Backfill/1.0 (https://vote.stgcaomenlibrary.top)"
API = "https://www.wikidata.org/w/api.php"
MIN_SIMILAR = 0.92
CAND_SIMILAR = 0.85

# Wikidata P400 平台标签 -> 站内 platform 键
PLATFORM_MAP = {
    "arcade game": "arcade", "arcade": "arcade",
    "microsoft windows": "pc", "windows": "pc",
    "playstation": "ps1", "playstation 2": "ps2", "playstation 3": "ps3",
    "playstation 4": "ps4", "playstation 5": "ps5",
    "playstation portable": "psp", "playstation vita": "vita",
    "super nintendo entertainment system": "snes", "super famicom": "snes",
    "nintendo entertainment system": "nes", "famicom": "nes",
    "mega drive": "md", "sega genesis": "md", "sega saturn": "saturn",
    "dreamcast": "dreamcast", "nintendo switch": "switch",
    "game boy": "gb", "game boy advance": "gba", "nintendo ds": "nds",
    "nintendo 3ds": "3ds", "nintendo 64": "n64", "gamecube": "gamecube",
    "wii": "wii", "xbox": "xbox", "xbox 360": "xbox360", "xbox one": "xboxone",
    "msx": "msx", "pc engine": "pce", "turbografx-16": "pce",
    "wonderswan": "wonderswan", "ios": "mobile", "android": "mobile",
    "macos": "mac", "classic mac os": "mac", "linux": "linux",
    "ms-dos": "dos", "dos": "dos",
}

NON_ALNUM = re.compile(r"[^0-9a-z]+")


def norm(text: str | None) -> str:
    if not text:
        return ""
    return NON_ALNUM.sub("", unicodedata.normalize("NFKC", text).lower())


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class Wiki:
    def __init__(self) -> None:
        self.cache: dict[str, object] = {}
        if CACHE_PATH.is_file():
            try:
                self.cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}
        self.calls = 0

    def _get(self, params: dict[str, str]):
        key = urllib.parse.urlencode(sorted(params.items()))
        if key in self.cache:
            return self.cache[key]
        req = urllib.request.Request(API + "?" + key, headers={"User-Agent": UA})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self.cache[key] = data
                self.calls += 1
                time.sleep(0.12)
                return data
            except Exception as exc:
                if attempt == 2:
                    print(f"  ! 请求失败: {exc}", file=sys.stderr)
                    return None
                time.sleep(1.5 * (attempt + 1))
        return None

    def search(self, text: str) -> list[dict]:
        data = self._get({
            "action": "wbsearchentities", "search": text, "language": "en",
            "uselang": "en", "type": "item", "limit": "8", "format": "json",
        })
        return (data or {}).get("search", [])

    def entities(self, qids: list[str]) -> dict:
        out: dict = {}
        qids = [q for q in qids if q]
        for i in range(0, len(qids), 50):
            chunk = qids[i : i + 50]
            data = self._get({
                "action": "wbgetentities", "ids": "|".join(chunk),
                "props": "claims|labels", "languages": "en|ja", "format": "json",
            })
            out.update((data or {}).get("entities", {}))
        return out

    def save(self) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def claim_values(entity: dict, prop: str) -> list:
    out = []
    for c in (entity.get("claims", {}) or {}).get(prop, []):
        try:
            out.append(c["mainsnak"]["datavalue"]["value"])
        except (KeyError, TypeError):
            continue
    return out


def has_company_info(entity: dict) -> bool:
    return bool(claim_values(entity, "P123") or claim_values(entity, "P178"))


def candidate_score(
    entity: dict, company: str, label_of: dict[str, str], sim: float
) -> float:
    """候选打分。

    相似度经常打平（"RefleX" 与 "Reflex" 归一化后都是 reflex），
    这时要靠「公司能对上」来区分：开发者写着 SITER SKAIN 的那条才是我们要的，
    而不是同名的 1987 年街机。有公司信息且对得上就加权，没有信息不加不减。
    """
    score = sim
    if has_company_info(entity) and company_matches(entity, company, label_of):
        score += 0.06
    if claim_values(entity, "P400"):
        score += 0.02
    if claim_values(entity, "P577"):
        score += 0.01
    return score


def year_from(entity: dict) -> int | None:
    """取发行年份：优先 P577（出版日期），没有就退到 P571（起始时间）。

    Wikidata 上不少游戏条目只填了 P571，只查 P577 会白白漏掉。
    """
    for prop in ("P577", "P571"):
        years = []
        for v in claim_values(entity, prop):
            if isinstance(v, dict):
                m = re.search(r"([+-])(\d{4})", v.get("time") or "")
                if m:
                    years.append(int(m.group(2)))
        if years:
            return min(years)
    return None


def looks_like_game(entity: dict, label_of: dict[str, str]) -> bool:
    """P31 里得有「game」类条目，否则可能命中同名电影/音乐专辑。"""
    labels = [
        label_of.get(v.get("id"), "").lower()
        for v in claim_values(entity, "P31")
        if isinstance(v, dict)
    ]
    return any("game" in lbl for lbl in labels if lbl)


def company_matches(entity: dict, company: str, label_of: dict[str, str]) -> bool:
    """发行商/开发商对得上才算同一款。同名不同作多半靠这条拦下。"""
    if not company:
        return True
    names: list[str] = []
    for prop in ("P123", "P178"):
        for v in claim_values(entity, prop):
            if isinstance(v, dict):
                lbl = label_of.get(v.get("id"), "")
                if lbl:
                    names.append(lbl)
    if not names:
        return True  # 对方没写公司，无法证伪
    target = norm(company)
    for n in names:
        nn = norm(n)
        if not nn:
            continue
        if target and (target in nn or nn in target):
            return True
        if similar(target, nn) >= 0.6:
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    wiki = Wiki()
    db = SessionLocal()
    try:
        games = (
            db.query(models.Game)
            .filter(
                (models.Game.release_year.is_(None)) | (models.Game.platform.is_(None))
            )
            .order_by(models.Game.id)
            .all()
        )
        if args.limit:
            games = games[: args.limit]
        print(f"待补全作品: {len(games)}")

        # --- 阶段 1：搜索，收集候选 ---
        cands: dict[int, list[tuple[str, float]]] = {}
        for idx, g in enumerate(games, 1):
            names = [g.title]
            names += [a.name for a in g.aliases][:3]
            names += [t.name for t in g.translations][:3]
            found: dict[str, float] = {}
            for name in names:
                target = norm(name)
                if not target:
                    continue
                for hit in wiki.search(name)[:8]:
                    score = similar(target, norm(hit.get("label")))
                    qid = hit["id"]
                    if score >= CAND_SIMILAR and score > found.get(qid, 0):
                        found[qid] = score
            if found:
                cands[g.id] = sorted(found.items(), key=lambda kv: -kv[1])[:5]
            if idx % 100 == 0:
                print(f"  …已搜索 {idx}/{len(games)}")

        print(f"有候选的作品: {len(cands)} / {len(games)}")

        # --- 阶段 2：批量拉实体 ---
        all_qids = sorted({q for lst in cands.values() for q, _ in lst})
        ents = wiki.entities(all_qids)
        print(f"拉取实体: {len(all_qids)} 个")

        # 一次把引用到的条目（P31 类型 / P123 发行商 / P178 开发商 / P400 平台）标签全拉回来
        ref_qids: set[str] = set()
        for q in all_qids:
            for prop in ("P31", "P123", "P178", "P400"):
                for v in claim_values(ents.get(q, {}), prop):
                    if isinstance(v, dict) and v.get("id"):
                        ref_qids.add(v["id"])
        ref_ents = wiki.entities(sorted(ref_qids))
        label_of = {
            q: ((e.get("labels", {}) or {}).get("en", {}) or {}).get("value", "")
            for q, e in ref_ents.items()
        }

        # --- 阶段 3：挑候选（先过类型与公司两道闸）---
        by_id = {g.id: g for g in games}
        chosen: dict[int, str] = {}
        rejected = 0
        for gid, lst in cands.items():
            good = [(q, s) for q, s in lst if s >= MIN_SIMILAR]
            if not good:
                continue
            g = by_id[gid]
            ok = []
            for q, s in good:
                ent = ents.get(q, {})
                if not looks_like_game(ent, label_of):
                    continue
                if not company_matches(ent, g.company, label_of):
                    continue
                ok.append((q, s))
            if not ok:
                rejected += 1
                continue
            with_claims = [
                (q, s) for q, s in ok
                if claim_values(ents.get(q, {}), "P577")
                or claim_values(ents.get(q, {}), "P400")
            ]
            pool = with_claims or ok
            chosen[gid] = max(
                pool,
                key=lambda kv: candidate_score(
                    ents.get(kv[0], {}), g.company, label_of, kv[1]
                ),
            )[0]
        print(f"最终采用: {len(chosen)}｜被闸门拦下: {rejected}")

        # --- 阶段 5：写入 ---
        filled_year = filled_plat = 0
        samples: list[str] = []
        for gid, qid in chosen.items():
            g = by_id[gid]
            ent = ents.get(qid, {})
            year = year_from(ent)
            keys: list[str] = []
            for v in claim_values(ent, "P400"):
                key = PLATFORM_MAP.get(label_of.get(v.get("id"), "").strip().lower())
                if key and key not in keys:
                    keys.append(key)

            if args.dry_run:
                if year and not g.release_year:
                    filled_year += 1
                    if len(samples) < 8:
                        samples.append(f"{g.title} → {year}")
                if keys and not g.platform:
                    filled_plat += 1
                continue

            changed = False
            if year and not g.release_year:
                g.release_year = year
                filled_year += 1
                if len(samples) < 8:
                    samples.append(f"{g.title} → {year}")
                changed = True
            if keys and not g.platform:
                # platform 列存中文展示名（「街机 / PC」），筛选走 ilike '%街机%'
                g.platform = " / ".join(PLATFORM_LABELS.get(k, k) for k in keys)
                filled_plat += 1
                changed = True
            if changed:
                db.flush()

        if not args.dry_run:
            db.commit()

        print("\n===== 补全结果 =====")
        print(f"补到年份: {filled_year}｜补到平台: {filled_plat}｜网络请求: {wiki.calls}")
        if samples:
            print("样例:", "；".join(samples))
        if args.dry_run:
            print("[dry-run] 未写入")
        else:
            print(
                "现有年份:",
                db.query(models.Game).filter(models.Game.release_year.isnot(None)).count(),
                "| 现有平台:",
                db.query(models.Game).filter(models.Game.platform.isnot(None)).count(),
            )
    finally:
        db.close()
        wiki.save()


if __name__ == "__main__":
    main()
