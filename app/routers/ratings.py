# app/routers/ratings.py
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from .. import models, database, auth
from fastapi.responses import JSONResponse
from typing import Optional
from app.utils.ratings import (
    get_updated_difficulty_scores_for_context,
    QUALITY_CATEGORY_MAP,
    DIFFICULTY_CATEGORY_MAP,
    get_updated_quality_scores,
    get_updated_difficulty_scores
)

router = APIRouter(
    prefix="/game",
    tags=["Ratings"]
)

@router.post("/{game_id}/rate_quality")
async def rate_game_quality(
    request: Request,
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    form_data = await request.form()
    
    # 解析品质评分数据（从配置动态读取字段名）
    from app.config.site_config import get_quality_dimensions
    quality_dims = get_quality_dimensions()
    
    ratings = {}
    for dim in quality_dims:
        field_name = dim["field"]
        # HTML中星级评分的name是 "rating_fun" 等（使用字段名）
        rating_value = form_data.get(f"rating_{field_name}")
        if rating_value and rating_value.isdigit():
            ratings[field_name] = int(rating_value)

    if not ratings:
        raise HTTPException(status_code=400, detail="没有提供任何有效的评分数据")

    existing_rating = db.query(models.QualityRating).filter_by(
        game_id=game_id, user_id=current_user.id
    ).first()

    if existing_rating:
        for field, value in ratings.items():
            setattr(existing_rating, field, value)
    else:
        new_rating = models.QualityRating(
            game_id=game_id, user_id=current_user.id, user_name=current_user.username, **ratings
        )
        db.add(new_rating)
    # +++ 结束 +++
    
    db.commit()

    # 计算并返回更新后的评分
    quality_ratings = db.query(models.QualityRating).filter_by(game_id=game_id).all()
    count = len(quality_ratings)
    total_score = sum((r.fun + r.core + r.depth + r.performance + r.story) / 5.0 for r in quality_ratings) / count if count else 0
    
    updated_scores = [{
        "category": cat,
        "raw_value": round(sum(getattr(r, field) for r in quality_ratings) / count, 2) if count else 0,
        "count": count
    } for cat, field in zip(QUALITY_CATEGORY_MAP.keys(), QUALITY_CATEGORY_MAP.values())]

    return JSONResponse(content={
        "status": "success",
        "message": "品质评分提交成功！",
        "updated_scores": updated_scores,
        "overall_score": round(total_score, 2)
    })


@router.delete("/{game_id}/rate_quality")
async def delete_game_quality_rating(
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """撤销当前用户对该游戏的品质评分"""
    existing_rating = db.query(models.QualityRating).filter_by(
        game_id=game_id, user_id=current_user.id
    ).first()

    if not existing_rating:
        raise HTTPException(status_code=404, detail="当前没有可撤销的品质评分")

    db.delete(existing_rating)
    db.commit()

    # 删除后返回更新的聚合结果，前端可选择刷新或按需更新
    updated_scores = get_updated_quality_scores(db, game_id)
    overall_score = 0.0
    if updated_scores:
        # overall = 所有维度平均，再对所有评分求平均
        ratings = db.query(models.QualityRating).filter_by(game_id=game_id).all()
        if ratings:
            count = len(ratings)
            overall_score = sum(
                (r.fun + r.core + r.depth + r.performance + r.story) / 5.0
                for r in ratings
            ) / count

    return JSONResponse(content={
        "status": "success",
        "message": "已撤销你的品质评分。",
        "updated_scores": updated_scores,
        "overall_score": round(overall_score, 2) if updated_scores else 0.0
    })
    
@router.post("/{game_id}/rate_difficulty")
async def rate_game_difficulty(
    request: Request,
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    form_data = await request.form()
    
    difficulty_id_str = form_data.get("difficulty_level_id")
    ship_id_str = form_data.get("ship_type_id")
    
    difficulty_level_id = int(difficulty_id_str) if difficulty_id_str and difficulty_id_str.isdigit() else None
    ship_type_id = int(ship_id_str) if ship_id_str and ship_id_str.isdigit() else None
    
    # 解析难度评分数据（从配置动态读取字段名）
    from app.config.site_config import get_difficulty_dimensions
    difficulty_dims = get_difficulty_dimensions()
    
    ratings = {}
    for dim in difficulty_dims:
        field_name = dim["field"]
        # HTML中输入框的name是 "rating_dodge" 等（使用字段名）
        rating_value = form_data.get(f"rating_{field_name}")
        if rating_value and rating_value.isdigit():
            ratings[field_name] = int(rating_value)

    if not ratings:
        raise HTTPException(status_code=400, detail="没有提供任何有效的评分数据")

    existing_rating = db.query(models.DifficultyRating).filter_by(
        game_id=game_id, 
        user_id=current_user.id,
        difficulty_level_id=difficulty_level_id,
        ship_type_id=ship_type_id
    ).first()

    if existing_rating:
        for field, value in ratings.items():
            setattr(existing_rating, field, value)
    else:
        new_rating = models.DifficultyRating(
            game_id=game_id, user_id=current_user.id, user_name=current_user.username,
            difficulty_level_id=difficulty_level_id, ship_type_id=ship_type_id, **ratings
        )
        db.add(new_rating)
    db.commit()

    # 计算并返回更新后的评分
    updated_context_data = get_updated_difficulty_scores_for_context(db, game_id, difficulty_level_id, ship_type_id)
    context_key = f"d{difficulty_level_id or 0}_s{ship_type_id or 0}"

    return JSONResponse(content={
        "status": "success",
        "message": "难度评分提交成功！",
        "updated_context_key": context_key,
        "updated_context_data": updated_context_data
    })


@router.delete("/{game_id}/rate_difficulty")
async def delete_game_difficulty_rating(
    game_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    撤销当前用户在指定情境下的难度评分。
    通过查询参数 difficulty_level_id / ship_type_id 来定位情境；
    为空则视为总体/全机体（即 NULL）。
    """
    params = request.query_params
    difficulty_id_str = params.get("difficulty_level_id")
    ship_id_str = params.get("ship_type_id")

    difficulty_level_id = int(difficulty_id_str) if difficulty_id_str and difficulty_id_str.isdigit() else None
    ship_type_id = int(ship_id_str) if ship_id_str and ship_id_str.isdigit() else None

    existing_rating = db.query(models.DifficultyRating).filter_by(
        game_id=game_id,
        user_id=current_user.id,
        difficulty_level_id=difficulty_level_id,
        ship_type_id=ship_type_id
    ).first()

    if not existing_rating:
        raise HTTPException(status_code=404, detail="当前情境下没有可撤销的难度评分")

    db.delete(existing_rating)
    db.commit()

    # 返回当前情境以及整体的更新后数据，前端可按需使用
    updated_context_data = get_updated_difficulty_scores_for_context(
        db, game_id, difficulty_level_id, ship_type_id
    )
    updated_overall = get_updated_difficulty_scores(db, game_id)

    context_key = f"d{difficulty_level_id or 0}_s{ship_type_id or 0}"

    return JSONResponse(content={
        "status": "success",
        "message": "已撤销你在该情境下的难度评分。",
        "updated_context_key": context_key,
        "updated_context_data": updated_context_data,
        "updated_overall": updated_overall
    })