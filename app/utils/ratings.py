"""
评分相关的辅助函数和常量
"""
from typing import Dict, Any, List, Optional
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
    
    total_avg, valid_dims = 0, 0
    for score_data in category_scores:
        if score_data['count'] > 0:
            total_avg += score_data['raw_value']
            valid_dims += 1
    
    context_data['categories'] = category_scores
    context_data['overall_avg'] = round(total_avg / valid_dims, 2) if valid_dims > 0 else 0.0
    context_data['total_ratings'] = len(ratings_in_context)
    
    return context_data


def get_updated_quality_scores(db: Session, game_id: int) -> List[Dict[str, Any]]:
    """获取更新后的品质分数"""
    ratings = db.query(models.QualityRating).filter(models.QualityRating.game_id == game_id).all()
    if not ratings:
        return []
    
    count = len(ratings)
    
    return [{
        "category": cat,
        "raw_value": round(sum(getattr(r, field) for r in ratings) / count, 2)
    } for cat, field in zip(QUALITY_CATEGORIES, QUALITY_FIELDS)]


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
    
    if quality_ratings:
        total_quality = sum((r.fun + r.core + r.depth + r.performance + r.story) / 5.0 for r in quality_ratings)
        evaluation["overall_quality_score"] = round(total_quality / quality_ratings_count, 2)
        evaluation["quality_scores"] = [{
            "category": cat_name, 
            "raw_value": round(sum(getattr(r, field_name) for r in quality_ratings) / quality_ratings_count, 2),
            "count": quality_ratings_count
        } for cat_name, field_name in zip(QUALITY_CATEGORIES, QUALITY_FIELDS)]
    else:
        evaluation["overall_quality_score"] = 0.0
        evaluation["quality_scores"] = [{"category": cat, "raw_value": 0, "count": 0} for cat in QUALITY_CATEGORIES]
    
    evaluation["comments"] = sorted([{
        "id": c.id, "content": c.content,
        "user_id": c.author_id, "user_name": c.user_name
    } for c in game.comments], key=lambda x: x['id'], reverse=True)

    # 2. 难度部分：按情境分组计算
    difficulty_ratings = game.difficulty_ratings
    evaluation["difficulty_scores_by_context"] = {}
    
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
        
        total_avg, valid_dims = 0, 0
        for score_data in category_scores:
            if score_data['count'] > 0:
                total_avg += score_data['raw_value']
                valid_dims += 1
        
        context_data['categories'] = category_scores
        context_data['overall_avg'] = round(total_avg / valid_dims, 2) if valid_dims > 0 else 0.0
        context_data['total_ratings'] = len(ratings_in_context)

        context_key = f"d{diff_id or 0}_s{ship_id or 0}"
        evaluation["difficulty_scores_by_context"][context_key] = context_data

    # 3. 计算游戏总体的难度均分
    if difficulty_ratings:
        total_difficulty_sum, valid_ratings_count = 0, 0
        for r in difficulty_ratings:
            dims = [d for d in [r.dodge, r.strategy, r.execution] if d is not None]
            if dims:
                total_difficulty_sum += sum(dims) / len(dims)
                valid_ratings_count += 1
        
        overall_score = round(total_difficulty_sum / valid_ratings_count, 2) if valid_ratings_count > 0 else 0.0
        evaluation["overall_difficulty_score"] = overall_score
        evaluation["overall_difficulty_realm"] = get_difficulty_realm(overall_score).split(' ')[0]
    else:
        evaluation["overall_difficulty_score"] = 0.0
        evaluation["overall_difficulty_realm"] = "N/A"
    
    return evaluation
