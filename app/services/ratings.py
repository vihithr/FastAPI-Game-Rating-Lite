"""
评分相关的辅助函数和常量
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session  # type: ignore
from itertools import groupby
from .. import models

# 类别映射常量
QUALITY_CATEGORIES = ["趣味性", "核心设计", "深度", "演出", "剧情"]
QUALITY_FIELDS = ["fun", "core", "depth", "performance", "story"]

DIFFICULTY_CATEGORIES = ["避弹", "策略", "执行"]
DIFFICULTY_FIELDS = ["dodge", "strategy", "execution"]

QUALITY_CATEGORY_MAP = dict(zip(QUALITY_CATEGORIES, QUALITY_FIELDS))
DIFFICULTY_CATEGORY_MAP = dict(zip(DIFFICULTY_CATEGORIES, DIFFICULTY_FIELDS))

QUALITY_MIN, QUALITY_MAX = 1, 10
DIFFICULTY_MIN, DIFFICULTY_MAX = 1, 60


def parse_rating_dimensions(
    form_data, category_map, minimum: int, maximum: int
) -> Dict[str, int]:
    """解析并校验所有评分维度，缺一不可，且必须落在指定范围内。"""
    ratings = {}
    missing = []
    for cat_name, field_name in category_map.items():
        raw_value = form_data.get(f"rating_{cat_name}")
        if raw_value is None or str(raw_value).strip() == "":
            missing.append(cat_name)
            continue
        try:
            value = int(str(raw_value).strip())
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"“{cat_name}”评分必须是整数")
        if value < minimum or value > maximum:
            raise HTTPException(
                status_code=400,
                detail=f"“{cat_name}”评分必须在 {minimum}-{maximum} 之间",
            )
        ratings[field_name] = value

    if missing:
        raise HTTPException(
            status_code=400,
            detail="请填写所有评分维度：" + "、".join(missing),
        )
    return ratings


def parse_quick_quality(raw_value) -> float:
    """解析快速整体品质分：1-10，支持 0.5 步进。"""
    if raw_value is None or str(raw_value).strip() == "":
        raise HTTPException(
            status_code=400,
            detail="请选择一个整体品质分（1-10，支持 0.5 步进）",
        )
    try:
        value = Decimal(str(raw_value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="整体品质评分必须是 1-10 之间的数字",
        )
    if not value.is_finite():
        raise HTTPException(
            status_code=400,
            detail="整体品质评分必须是 1-10 之间的数字",
        )
    if value < Decimal("1") or value > Decimal("10"):
        raise HTTPException(
            status_code=400,
            detail="整体品质评分必须在 1.0-10.0 之间",
        )
    if (value * 2) != (value * 2).to_integral_value():
        raise HTTPException(
            status_code=400,
            detail="整体品质评分必须以 0.5 为步进（例如 7.5）",
        )
    return float(value)


def parse_quick_difficulty(form_data) -> Optional[int]:
    """解析可选的快速整体难度分；未开启时返回 None。"""
    include = form_data.get("include_difficulty")
    if include is None or str(include).strip().lower() in ("", "0", "false", "off", "no"):
        return None
    raw_value = form_data.get("quick_difficulty")
    if raw_value is None or str(raw_value).strip() == "":
        raise HTTPException(
            status_code=400,
            detail="请填写整体难度评分，或关闭难度评分",
        )
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="整体难度评分必须是 1-60 之间的整数",
        )
    if value < DIFFICULTY_MIN or value > DIFFICULTY_MAX:
        raise HTTPException(
            status_code=400,
            detail="整体难度评分必须在 1-60 之间",
        )
    return value


def parse_optional_context_id(raw_value, label: str) -> Optional[int]:
    """把空值/0 解析为 None（总体/全机体），其余必须是正整数。"""
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if text in ("", "0"):
        return None
    try:
        value = int(text)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"无效的{label}")
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"无效的{label}")
    return value


def ensure_game_exists(db: Session, game_id: int) -> None:
    game = db.query(models.Game.id).filter(models.Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")


def validate_difficulty_context(
    db: Session,
    game_id: int,
    difficulty_level_id: Optional[int],
    ship_type_id: Optional[int],
) -> None:
    if difficulty_level_id is not None:
        exists = (
            db.query(models.DifficultyLevel.id)
            .filter_by(id=difficulty_level_id, game_id=game_id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=400, detail="难度等级不属于该游戏")
    if ship_type_id is not None:
        exists = (
            db.query(models.ShipType.id)
            .filter_by(id=ship_type_id, game_id=game_id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=400, detail="机体/角色不属于该游戏")


def upsert_quality_rating(
    db: Session,
    game_id: int,
    user_id: int,
    user_name: str,
    ratings: Dict[str, int],
    overall: Optional[float] = None,
) -> None:
    """写入品质评分；细分提交会清空 overall，快速提交会清空五维。"""
    fields = {field: ratings.get(field) for field in QUALITY_FIELDS}
    fields["overall"] = overall

    existing = (
        db.query(models.QualityRating)
        .filter_by(game_id=game_id, user_id=user_id)
        .first()
    )
    if existing:
        for field, value in fields.items():
            setattr(existing, field, value)
    else:
        db.add(
            models.QualityRating(
                game_id=game_id,
                user_id=user_id,
                user_name=user_name,
                **fields,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.QualityRating)
            .filter_by(game_id=game_id, user_id=user_id)
            .first()
        )
        if existing is None:
            raise
        for field, value in fields.items():
            setattr(existing, field, value)
        db.commit()


def upsert_difficulty_rating(
    db: Session,
    game_id: int,
    user_id: int,
    user_name: str,
    difficulty_level_id: Optional[int],
    ship_type_id: Optional[int],
    ratings: Dict[str, int],
    overall: Optional[float] = None,
) -> None:
    """写入难度评分；细分提交会清空 overall，快速提交会清空三维。"""
    fields = {field: ratings.get(field) for field in DIFFICULTY_FIELDS}
    fields["overall"] = overall

    filters = {
        "game_id": game_id,
        "user_id": user_id,
        "difficulty_level_id": difficulty_level_id,
        "ship_type_id": ship_type_id,
    }
    existing = db.query(models.DifficultyRating).filter_by(**filters).first()
    if existing:
        for field, value in fields.items():
            setattr(existing, field, value)
    else:
        db.add(
            models.DifficultyRating(
                user_name=user_name,
                **filters,
                **fields,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.DifficultyRating).filter_by(**filters).first()
        if existing is None:
            raise
        for field, value in fields.items():
            setattr(existing, field, value)
        db.commit()


def upsert_quick_ratings(
    db: Session,
    game_id: int,
    user_id: int,
    user_name: str,
    quality_overall: float,
    difficulty_overall: Optional[int],
) -> None:
    """原子写入快速品质分，以及可选的快速整体难度分。"""
    quality_fields = {field: None for field in QUALITY_FIELDS}
    quality_fields["overall"] = quality_overall
    difficulty_fields = {field: None for field in DIFFICULTY_FIELDS}
    difficulty_fields["overall"] = difficulty_overall

    def apply_quality() -> None:
        rating = (
            db.query(models.QualityRating)
            .filter_by(game_id=game_id, user_id=user_id)
            .first()
        )
        if rating is None:
            db.add(
                models.QualityRating(
                    game_id=game_id,
                    user_id=user_id,
                    user_name=user_name,
                    **quality_fields,
                )
            )
            return
        for field, value in quality_fields.items():
            setattr(rating, field, value)

    def apply_difficulty() -> None:
        if difficulty_overall is None:
            return
        rating = (
            db.query(models.DifficultyRating)
            .filter_by(
                game_id=game_id,
                user_id=user_id,
                difficulty_level_id=None,
                ship_type_id=None,
            )
            .first()
        )
        if rating is None:
            db.add(
                models.DifficultyRating(
                    game_id=game_id,
                    user_id=user_id,
                    user_name=user_name,
                    difficulty_level_id=None,
                    ship_type_id=None,
                    **difficulty_fields,
                )
            )
            return
        for field, value in difficulty_fields.items():
            setattr(rating, field, value)

    apply_quality()
    apply_difficulty()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        apply_quality()
        apply_difficulty()
        db.commit()


def get_quality_row_score(rating: models.QualityRating) -> Optional[float]:
    """单条品质评分的整体分：快速分优先，否则取非空维度均值。"""
    if rating.overall is not None:
        return float(rating.overall)
    values = [
        getattr(rating, field)
        for field in QUALITY_FIELDS
        if getattr(rating, field) is not None
    ]
    return sum(values) / len(values) if values else None


def get_difficulty_row_score(rating: models.DifficultyRating) -> Optional[float]:
    """单条难度评分的整体分：快速分优先，否则取非空维度均值。"""
    if rating.overall is not None:
        return float(rating.overall)
    values = [
        getattr(rating, field)
        for field in DIFFICULTY_FIELDS
        if getattr(rating, field) is not None
    ]
    return sum(values) / len(values) if values else None


def get_quality_rating_mode(rating: models.QualityRating) -> str:
    if rating.overall is not None:
        return "quick"
    if any(getattr(rating, field) is not None for field in QUALITY_FIELDS):
        return "detailed"
    return "empty"


def get_difficulty_rating_mode(rating: models.DifficultyRating) -> str:
    if rating.overall is not None:
        return "quick"
    if any(getattr(rating, field) is not None for field in DIFFICULTY_FIELDS):
        return "detailed"
    return "empty"


def _row_score_expr(model, dims):
    """SQL 版本的单行整体分：overall 优先，否则取非空维度均值。"""
    total = sum(func.coalesce(getattr(model, field), 0) for field in dims)
    present = sum(
        case((getattr(model, field).is_not(None), 1), else_=0)
        for field in dims
    )
    return func.coalesce(model.overall, total / func.nullif(present, 0))


def quality_row_score_expr():
    return _row_score_expr(models.QualityRating, QUALITY_FIELDS)


def difficulty_row_score_expr():
    return _row_score_expr(models.DifficultyRating, DIFFICULTY_FIELDS)


def get_quality_overall_score(rating: models.QualityRating) -> Optional[float]:
    """兼容旧调用：单条品质评分的整体分。"""
    return get_quality_row_score(rating)


def get_quality_overall_average(ratings: List[models.QualityRating]) -> float:
    """所有品质评分的总体平均分；忽略没有任何维度的空记录。"""
    scores = []
    for rating in ratings:
        score = get_quality_overall_score(rating)
        if score is not None:
            scores.append(score)
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def get_difficulty_realm(score: float) -> str:
    """根据难度均分返回段位描述字符串"""
    if score <= 0:
        return "N/A"
    if score <= 5:
        return f"见习一 ({score:.1f}/60)"
    if score <= 10:
        return f"见习二 ({score:.1f}/60)"
    if score <= 15:
        return f"新手一 ({score:.1f}/60)"
    if score <= 20:
        return f"新手二 ({score:.1f}/60)"
    if score <= 25:
        return f"入门一 ({score:.1f}/60)"
    if score <= 30:
        return f"入门二 ({score:.1f}/60)"
    if score <= 35:
        return f"进阶一 ({score:.1f}/60)"
    if score <= 40:
        return f"进阶二 ({score:.1f}/60)"
    if score <= 45:
        return f"上级一 ({score:.1f}/60)"
    if score <= 50:
        return f"上级二 ({score:.1f}/60)"
    if score <= 55:
        return f"上级三 ({score:.1f}/60)"
    return f"论外 ({score:.1f}/60)"


def get_updated_difficulty_scores_for_context(
    db: Session, game_id: int, diff_id: Optional[int], ship_id: Optional[int]
) -> Dict[str, Any]:
    """计算特定情境（难度等级+机体类型）的难度分数"""
    ratings_in_context = db.query(models.DifficultyRating).filter_by(
        game_id=game_id,
        difficulty_level_id=diff_id,
        ship_type_id=ship_id
    ).all()

    if not ratings_in_context:
        return {}
    
    context_data = {
        "difficulty_level_id": diff_id or 0,
        "ship_type_id": ship_id or 0
    }
    category_scores = []
    
    for cat_name, field_name in zip(DIFFICULTY_CATEGORIES, DIFFICULTY_FIELDS):
        valid_scores = [getattr(r, field_name) for r in ratings_in_context if getattr(r, field_name) is not None]
        count = len(valid_scores)
        avg = sum(valid_scores) / count if count > 0 else 0
        category_scores.append({
            "category": cat_name, 
            "raw_value": round(avg, 2),
            "count": count, 
            "value": get_difficulty_realm(avg)
        })
    
    row_scores = [
        score for score in (get_difficulty_row_score(r) for r in ratings_in_context)
        if score is not None
    ]
    context_data['categories'] = category_scores
    context_data['overall_avg'] = (
        round(sum(row_scores) / len(row_scores), 2) if row_scores else 0.0
    )
    context_data['total_ratings'] = len(ratings_in_context)
    context_data['is_global'] = False

    return context_data


def get_global_difficulty_context(
    ratings: List[models.DifficultyRating],
) -> Dict[str, Any]:
    """所有难度评分的全局聚合，用于“游戏总体 | 全机体”视图。"""
    if not ratings:
        return {}

    scored = [r for r in ratings if get_difficulty_row_score(r) is not None]
    if not scored:
        return {}

    categories = []
    for cat_name, field_name in zip(DIFFICULTY_CATEGORIES, DIFFICULTY_FIELDS):
        values = [
            getattr(r, field_name)
            for r in ratings
            if getattr(r, field_name) is not None
        ]
        count = len(values)
        avg = sum(values) / count if count > 0 else 0
        categories.append({
            "category": cat_name,
            "raw_value": round(avg, 2),
            "count": count,
            "value": get_difficulty_realm(avg),
        })

    overall = sum(get_difficulty_row_score(r) for r in scored) / len(scored)
    quick_count = sum(1 for r in scored if r.overall is not None)
    return {
        "difficulty_level_id": 0,
        "ship_type_id": 0,
        "categories": categories,
        "overall_avg": round(overall, 2),
        "total_ratings": len(scored),
        "quick_ratings_count": quick_count,
        "detailed_ratings_count": len(scored) - quick_count,
        "is_global": True,
    }


def get_updated_quality_scores(db: Session, game_id: int) -> List[Dict[str, Any]]:
    """获取更新后的品质分数（逐维度过滤缺失值，避免旧数据导致 500）。"""
    ratings = db.query(models.QualityRating).filter(models.QualityRating.game_id == game_id).all()

    results = []
    for cat, field in zip(QUALITY_CATEGORIES, QUALITY_FIELDS):
        values = [
            getattr(r, field)
            for r in ratings
            if getattr(r, field) is not None
        ]
        results.append({
            "category": cat,
            "raw_value": round(sum(values) / len(values), 2) if values else 0,
            "count": len(values),
        })
    return results


def get_updated_difficulty_scores(db: Session, game_id: int) -> List[Dict[str, Any]]:
    """获取更新后的难度分数（包含段位值）"""
    ratings = db.query(models.DifficultyRating).filter(models.DifficultyRating.game_id == game_id).all()
    if not ratings:
        return []
    
    results = []
    for cat, field in zip(DIFFICULTY_CATEGORIES, DIFFICULTY_FIELDS):
        valid_scores = [getattr(r, field) for r in ratings if getattr(r, field) is not None]
        avg_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0
        results.append({
            "category": cat,
            "raw_value": avg_score,
            "value": get_difficulty_realm(avg_score)
        })
    return results


def get_game_evaluation(game: models.Game) -> Dict[str, Any]:
    """
    计算游戏的综合评价分数。
    - 品质部分：计算各维度的平均分
    - 难度部分：按 (difficulty_level_id, ship_type_id) 的组合进行分组计算
    """
    evaluation = {}
    
    # 1. 品质和评论部分
    quality_ratings = game.quality_ratings
    quality_ratings_count = len(quality_ratings)
    evaluation["quality_ratings_count"] = quality_ratings_count
    evaluation["overall_quality_score"] = get_quality_overall_average(quality_ratings)

    quality_scores = []
    for cat_name, field_name in zip(QUALITY_CATEGORIES, QUALITY_FIELDS):
        values = [
            getattr(r, field_name)
            for r in quality_ratings
            if getattr(r, field_name) is not None
        ]
        quality_scores.append({
            "category": cat_name,
            "raw_value": round(sum(values) / len(values), 2) if values else 0,
            "count": len(values),
        })
    evaluation["quality_scores"] = quality_scores

    distribution = {score: 0 for score in range(1, 11)}
    for rating in quality_ratings:
        score = get_quality_row_score(rating)
        if score is None:
            continue
        bucket = max(1, min(10, int(score + 0.5)))
        distribution[bucket] += 1
    evaluation["quality_distribution"] = [
        {"score": score, "count": distribution[score]}
        for score in range(1, 11)
    ]

    recent_ratings = []
    rated_quality = [
        rating for rating in quality_ratings
        if get_quality_row_score(rating) is not None
    ]
    for rating in sorted(
        rated_quality,
        key=lambda item: item.created_at or datetime.min,
        reverse=True,
    )[:4]:
        created = rating.created_at
        recent_ratings.append({
            "user_name": rating.user_name or "匿名玩家",
            "score": round(float(get_quality_row_score(rating)), 1),
            "mode": get_quality_rating_mode(rating),
            "created_at": created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else "",
        })
    evaluation["recent_quality_ratings"] = recent_ratings

    evaluation["comments"] = sorted([{
        "id": c.id, "content": c.content,
        "user_id": c.author_id, "user_name": c.user_name
    } for c in game.comments], key=lambda x: x['id'], reverse=True)

    # 2. 难度部分：按情境分组计算
    difficulty_ratings = game.difficulty_ratings
    evaluation["difficulty_scores_by_context"] = {}
    evaluation["difficulty_ratings_count"] = len(difficulty_ratings)
    
    sort_key = lambda r: (r.difficulty_level_id or 0, r.ship_type_id or 0)
    
    for context_ids, ratings_in_context_iter in groupby(sorted(difficulty_ratings, key=sort_key), key=sort_key):
        diff_id, ship_id = context_ids
        ratings_in_context = list(ratings_in_context_iter)
        
        context_data = {
            "difficulty_level_id": diff_id or 0,
            "ship_type_id": ship_id or 0
        }
        category_scores = []
        
        for cat_name, field_name in zip(DIFFICULTY_CATEGORIES, DIFFICULTY_FIELDS):
            valid_scores = [getattr(r, field_name) for r in ratings_in_context if getattr(r, field_name) is not None]
            count = len(valid_scores)
            avg = sum(valid_scores) / count if count > 0 else 0
            category_scores.append({
                "category": cat_name, 
                "raw_value": round(avg, 2),
                "count": count, 
                "value": get_difficulty_realm(avg)
            })
        
        row_scores = [
            score for score in (get_difficulty_row_score(r) for r in ratings_in_context)
            if score is not None
        ]
        context_data['categories'] = category_scores
        context_data['overall_avg'] = (
            round(sum(row_scores) / len(row_scores), 2) if row_scores else 0.0
        )
        context_data['total_ratings'] = len(ratings_in_context)
        context_data['is_global'] = False

        context_key = f"d{diff_id or 0}_s{ship_id or 0}"
        evaluation["difficulty_scores_by_context"][context_key] = context_data

    # 3. 游戏总体：所有难度评分的全局聚合；始终以 d0_s0 提供给前端
    level_counts = {}
    for context_data in evaluation["difficulty_scores_by_context"].values():
        if context_data.get("is_global"):
            continue
        level_key = str(context_data.get("difficulty_level_id") or 0)
        level_counts[level_key] = level_counts.get(level_key, 0) + context_data.get("total_ratings", 0)
    evaluation["difficulty_level_counts"] = level_counts

    global_context = get_global_difficulty_context(difficulty_ratings)
    if global_context:
        evaluation["difficulty_scores_by_context"]["d0_s0"] = global_context
        overall_score = global_context["overall_avg"]
        evaluation["overall_difficulty_score"] = overall_score
        evaluation["overall_difficulty_realm"] = get_difficulty_realm(overall_score).split(' ')[0]
    else:
        evaluation["overall_difficulty_score"] = 0.0
        evaluation["overall_difficulty_realm"] = "N/A"
    
    return evaluation


def build_user_ratings(
    db: Session,
    game_id: int,
    user_id: Optional[int],
) -> Dict[str, Any]:
    """当前用户对某游戏的评分，供页面 bootstrap 与 my-ratings API 共用。"""
    result: Dict[str, Any] = {"quality": None, "difficulty": {}}
    if user_id is None:
        return result

    quality = (
        db.query(models.QualityRating)
        .filter_by(game_id=game_id, user_id=user_id)
        .first()
    )
    if quality:
        result["quality"] = {
            "fun": quality.fun,
            "core": quality.core,
            "depth": quality.depth,
            "performance": quality.performance,
            "story": quality.story,
            "overall": quality.overall,
            "mode": get_quality_rating_mode(quality),
        }

    difficulty_ratings = (
        db.query(models.DifficultyRating)
        .filter_by(game_id=game_id, user_id=user_id)
        .all()
    )
    for rating in difficulty_ratings:
        context_key = f"d{rating.difficulty_level_id or 0}_s{rating.ship_type_id or 0}"
        result["difficulty"][context_key] = {
            "dodge": rating.dodge,
            "strategy": rating.strategy,
            "execution": rating.execution,
            "overall": rating.overall,
            "mode": get_difficulty_rating_mode(rating),
            "difficulty_level_id": rating.difficulty_level_id,
            "ship_type_id": rating.ship_type_id,
        }

    return result
