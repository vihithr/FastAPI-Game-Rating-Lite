#!/usr/bin/env python3
"""合并「同一款游戏被录了两条」的重复条目。

分组来自人工核实的 49 组（子代理逐组比对标题/别名/译名/公司后确认），
不用纯字符串规则去猜——因为「Darius vs Darius Twin」这类系列作，
归一化后一个串是另一个的前缀，机器很容易误合并。

保留规则（按优先级）：
1. 已有评分（用户数据最稀缺，尽量不迁移）
2. 中文简介（本站是中文站；采集来的英文简介都是维基原文截断到 420 字）
3. 有封面
4. 标签更多
5. 简介更长

合并动作：
- 评分/评论迁到保留条；撞唯一索引的（同一用户已给保留条打过分）删掉重复那条
- 难度等级、机体按名字对齐，能对上就复用，对不上就改挂到保留条
- 标签、别名、译名取并集；保留条缺的封面/简介/平台/年份/系列用重复条补

用法：
    venv/bin/python tools/dedup_games.py --report
    venv/bin/python tools/dedup_games.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

CJK = re.compile(r"[\u3400-\u9fff]")

# 人工核实的重复组。每组内第一条不一定是保留条，保留哪条由下面的评分函数决定。
PLAN: list[list[int]] = [
    [2, 255],            # 怒首领蜂 / DoDonPachi
    [6, 297],            # 长空超翼神 / Espgaluda
    [7, 146],            # 空战之路 / Battle Garegga
    [8, 245],            # 死亡微笑 / Deathsmiles
    [9, 257],            # 怒首领蜂大往生 / DoDonPachi DaiOuJou
    [12, 256, 262],      # 怒首领蜂大复活 / DaiFukkatsu / Resurrection
    [13, 269],           # 首领蜂 / DonPachi
    [14, 296],           # 长空超少年 / ESP Ra.De.
    [15, 232],           # 弹铳 / Dangun Feveron
    [16, 373],           # 狱门山物语 / Guwange
    [17, 577, 578],      # 能源之岚 / Progear / Progear no Arashi
    [18, 442],           # 决意：地狱中的羁绊 / Ketsui
    [19, 524],           # 虫姬 / Mushihimesama
    [20, 32, 237],       # 大流士战机（含标题带前导空格那条）/ Darius
    [21, 406],           # 铸蔷薇 / Ibara
    [22, 298],           # 长空超翼神2 / Espgaluda II
    [24, 571],           # 粉红甜心 / Pink Sweets
    [25, 240],           # 大流士战机 2 / Darius II
    [26, 525],           # 虫姬2 / Mushihimesama Futari
    [27, 520],           # 骑猪少女 / Muchi Muchi Pork!
    [28, 241],           # 大流士战机 双生 / Darius Twin
    [30, 238],           # 大流士战机 军团 / Darius Force
    [31, 246],           # 死亡微笑2 / Deathsmiles II
    [33, 89],            # 赤刀 / Akai Katana
    [34, 239],           # 大流士战机 外传 / Darius Gaiden
    [35, 263],           # 怒首领蜂最大往生 / SaiDaiOuJou
    [36, 324],           # G-大流士战机 / G-Darius
    [37, 242],           # 大流士战机 爆裂 / Dariusburst
    [39, 243],           # 爆裂 另一段编年史 / Dariusburst Another Chronicle
    [44, 136],           # 银河风暴 / Axelay
    [53, 779],           # 雷鸟3 / Thunder Force III
    [54, 780],           # 雷鸟4 / Thunder Force IV
    [55, 781],           # 雷鸟5 / Thunder Force V
    [57, 431],           # 神威 / KAMUI
    [61, 90],            # ∀kashicverse / Akashicverse（∀→V）
    [91, 92],            # AKE-BRE / Ake-Bre: Morning Star Girls
    [131, 132],          # Assault Shell / 带版本号后缀
    [189, 190],          # Cambria Sword / 带副标题
    [225, 226],          # Cyvern / Cyvern: The Dragon Weapons
    [283, 284],          # Eden Aegis / Eden's Aegis
    [418, 419],          # Jamestown / 带副标题
    [424, 425],          # Jikkyou / Jikkyō（长音符号）
    [484, 707],          # 魔法大作戦 / Sorcer Striker（日名 vs 欧美名）
    [688, 689],          # Sisters Royale / 带副标题
    [806, 807],          # Touhou 19 标题格式差异
    [830, 831],          # Touhou Madara Sakura / Madarazakusa（空格）
    [254, 357],          # Dimahoo / Great Mahou Daisakusen
    [446, 679],          # Kingdom Grand Prix / Shippu Mahou Daisakusen
    [522, 523],          # MUSHA / Musha Aleste（美日版名）
]


def has_cjk(text: str | None) -> bool:
    return bool(text and CJK.search(text))


def score(game: models.Game) -> tuple:
    """保留条的优先级。

    中文标题排第一：站内原有的 60 部都是中文名，用户看惯了；英文/日文名会作为
    别名补进去，搜索照样命中。其余依次是评分、中文简介、封面、标签数。
    """
    return (
        1 if has_cjk(game.title) else 0,
        len(game.quality_ratings) + len(game.difficulty_ratings),
        1 if has_cjk(game.description) else 0,
        1 if game.image_url else 0,
        len(game.tags),
        len(game.description or ""),
    )


def better_desc(dst: str | None, src: str | None) -> str | None:
    """中文简介优先；都中文或都英文时取更长的。"""
    if not src:
        return dst
    if not dst:
        return src
    if has_cjk(src) and not has_cjk(dst):
        return src
    if has_cjk(dst) and not has_cjk(src):
        return dst
    return src if len(src) > len(dst) else dst


def move_levels(db, src: models.Game, dst: models.Game) -> None:
    """难度等级/机体：dst 有同名项就复用，否则改挂到 dst 名下。"""
    for attr, model, ref in (
        ("difficulty_levels", models.DifficultyLevel, "difficulty_level_id"),
        ("ship_types", models.ShipType, "ship_type_id"),
    ):
        for item in list(getattr(src, attr)):
            twin = (
                db.query(model)
                .filter(model.game_id == dst.id, model.name == item.name)
                .first()
            )
            if twin is not None:
                db.query(models.DifficultyRating).filter(
                    getattr(models.DifficultyRating, ref) == item.id
                ).update({ref: twin.id}, synchronize_session=False)
                db.delete(item)
            else:
                item.game_id = dst.id


def merge(db, src: models.Game, dst: models.Game) -> dict:
    stats = {"q": 0, "d": 0, "comment": 0, "tag": 0}

    move_levels(db, src, dst)
    db.flush()

    for qr in list(src.quality_ratings):
        dup = (
            db.query(models.QualityRating)
            .filter_by(game_id=dst.id, user_id=qr.user_id)
            .first()
        )
        if dup:
            db.delete(qr)
        else:
            qr.game_id = dst.id
            stats["q"] += 1

    for dr in list(src.difficulty_ratings):
        q = db.query(models.DifficultyRating).filter(
            models.DifficultyRating.game_id == dst.id,
            models.DifficultyRating.user_id == dr.user_id,
        )
        if dr.difficulty_level_id is None:
            q = q.filter(models.DifficultyRating.difficulty_level_id.is_(None))
        else:
            q = q.filter(
                models.DifficultyRating.difficulty_level_id == dr.difficulty_level_id
            )
        if dr.ship_type_id is None:
            q = q.filter(models.DifficultyRating.ship_type_id.is_(None))
        else:
            q = q.filter(models.DifficultyRating.ship_type_id == dr.ship_type_id)
        if q.first():
            db.delete(dr)
        else:
            dr.game_id = dst.id
            stats["d"] += 1

    for c in list(src.comments):
        c.game_id = dst.id
        stats["comment"] += 1

    for tag in list(src.tags):
        if tag not in dst.tags:
            dst.tags.append(tag)
            stats["tag"] += 1

    seen = {a.name.lower() for a in dst.aliases}
    for a in list(src.aliases):
        if a.name.lower() in seen:
            db.delete(a)
        else:
            a.game_id = dst.id
            seen.add(a.name.lower())

    # 被删那条的标题必须留下来当别名，否则用英文名/日文名就搜不到了
    if src.title and src.title.strip().lower() not in seen:
        dst.aliases.append(models.Alias(name=src.title.strip()))
        seen.add(src.title.strip().lower())

    seen = {t.name.lower() for t in dst.translations}
    for t in list(src.translations):
        if t.name.lower() in seen:
            db.delete(t)
        else:
            t.game_id = dst.id
            seen.add(t.name.lower())

    if not dst.image_url and src.image_url:
        dst.image_url = src.image_url
    dst.description = better_desc(dst.description, src.description)
    for field in ("platform", "release_year", "series"):
        if not getattr(dst, field) and getattr(src, field):
            setattr(dst, field, getattr(src, field))

    db.flush()
    # 子项已搬走，让 src 重新读一次集合，否则 delete-orphan 会把刚迁走的评分一起删掉
    db.expire(src)
    db.delete(src)
    db.flush()

    # 去空格要放在删掉重复条之后：库里「 大流士战机」和「大流士战机」曾同时存在，
    # 先 strip 会撞 games.title 的 UNIQUE 约束。
    stripped = (dst.title or "").strip()
    if stripped != dst.title:
        dst.title = stripped
        db.flush()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.report or args.apply):
        ap.error("需要 --report 或 --apply")

    db = SessionLocal()
    try:
        by_id = {g.id: g for g in db.query(models.Game).all()}
        missing = [i for grp in PLAN for i in grp if i not in by_id]
        if missing:
            sys.exit(f"这些 id 在库里不存在，先核对: {missing}")

        seen: dict[int, int] = {}
        for idx, grp in enumerate(PLAN):
            for gid in grp:
                if gid in seen:
                    sys.exit(f"id {gid} 同时出现在第 {seen[gid] + 1} 组和第 {idx + 1} 组")
                seen[gid] = idx

        removed = 0
        for idx, grp in enumerate(PLAN, 1):
            games = sorted((by_id[i] for i in grp), key=score, reverse=True)
            keep, drops = games[0], games[1:]
            removed += len(drops)
            print(f"[{idx:>2}] 保留 #{keep.id} {keep.title}  ({keep.company})")
            for d in drops:
                print(f"      删 #{d.id} {d.title}  ({d.company})")
            if args.apply:
                for d in drops:
                    st = merge(db, d, keep)
                    print(f"      → 迁移 {st}")
                db.commit()

        print()
        if args.apply:
            print(f"合并完成：删除 {removed} 条，库内剩 {db.query(models.Game).count()} 部")
        else:
            print(f"[report] 共 {len(PLAN)} 组，将删除 {removed} 条，未改动数据库")
    finally:
        db.close()


if __name__ == "__main__":
    main()
