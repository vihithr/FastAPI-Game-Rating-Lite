# app/routers/ratings.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .. import models, database, auth
from fastapi.responses import JSONResponse
from app.services.ratings import (
    DIFFICULTY_CATEGORY_MAP,
    DIFFICULTY_MAX,
    DIFFICULTY_MIN,
    QUALITY_CATEGORY_MAP,
    QUALITY_MAX,
    QUALITY_MIN,
    ensure_game_exists,
    get_difficulty_realm,
    get_global_difficulty_context,
    get_quality_overall_average,
    get_updated_difficulty_scores_for_context,
    get_updated_quality_scores,
    parse_optional_context_id,
    parse_quick_difficulty,
    parse_quick_quality,
    parse_rating_dimensions,
    upsert_difficulty_rating,
    upsert_quality_rating,
    upsert_quick_ratings,
    validate_difficulty_context,
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

    ensure_game_exists(db, game_id)
    ratings = parse_rating_dimensions(
        form_data, QUALITY_CATEGORY_MAP, QUALITY_MIN, QUALITY_MAX
    )

    upsert_quality_rating(
        db, game_id, current_user.id, current_user.username, ratings,
        overall=None,
    )

    # 计算并返回更新后的评分
    quality_ratings = db.query(models.QualityRating).filter_by(game_id=game_id).all()
    updated_scores = get_updated_quality_scores(db, game_id)
    overall_score = get_quality_overall_average(quality_ratings)

    return JSONResponse(content={
        "status": "success",
        "message": "品质评分提交成功！",
        "updated_scores": updated_scores,
        "overall_score": overall_score,
        "ratings_count": len(quality_ratings),
        "user_rating": {"overall": None, "mode": "detailed"},
    })


@router.post("/{game_id}/rate_quick")
async def rate_game_quick(
    request: Request,
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """快速评分：整体品质分必填，整体难度分可选；一次请求原子写入。"""
    form_data = await request.form()

    ensure_game_exists(db, game_id)
    quality_overall = parse_quick_quality(form_data.get("quick_quality"))
    difficulty_overall = parse_quick_difficulty(form_data)

    upsert_quick_ratings(
        db,
        game_id,
        current_user.id,
        current_user.username,
        quality_overall,
        difficulty_overall,
    )

    quality_ratings = db.query(models.QualityRating).filter_by(game_id=game_id).all()
    difficulty_ratings = db.query(models.DifficultyRating).filter_by(game_id=game_id).all()
    global_difficulty = get_global_difficulty_context(difficulty_ratings)
    overall_difficulty_score = global_difficulty.get("overall_avg", 0.0)
    overall_difficulty_realm = (
        get_difficulty_realm(overall_difficulty_score).split(" ")[0]
        if overall_difficulty_score > 0 else "N/A"
    )

    return JSONResponse(content={
        "status": "success",
        "message": "快速评分已提交！",
        "user_quality": {"overall": quality_overall, "mode": "quick"},
        "user_difficulty_overall": (
            {"overall": difficulty_overall, "mode": "quick"}
            if difficulty_overall is not None else None
        ),
        "updated_scores": get_updated_quality_scores(db, game_id),
        "overall_score": get_quality_overall_average(quality_ratings),
        "ratings_count": len(quality_ratings),
        "difficulty_overall": global_difficulty,
        "overall_difficulty_score": overall_difficulty_score,
        "overall_difficulty_realm": overall_difficulty_realm,
        "difficulty_ratings_count": len(difficulty_ratings),
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
    quality_ratings = db.query(models.QualityRating).filter_by(game_id=game_id).all()
    return JSONResponse(content={
        "status": "success",
        "message": "已撤销你的品质评分。",
        "updated_scores": get_updated_quality_scores(db, game_id),
        "overall_score": get_quality_overall_average(quality_ratings),
        "ratings_count": len(quality_ratings),
    })
    
@router.post("/{game_id}/rate_difficulty")
async def rate_game_difficulty(
    request: Request,
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    form_data = await request.form()

    ensure_game_exists(db, game_id)

    difficulty_level_id = parse_optional_context_id(
        form_data.get("difficulty_level_id"), "难度等级"
    )
    ship_type_id = parse_optional_context_id(
        form_data.get("ship_type_id"), "机体类型"
    )
    validate_difficulty_context(db, game_id, difficulty_level_id, ship_type_id)

    ratings = parse_rating_dimensions(
        form_data, DIFFICULTY_CATEGORY_MAP, DIFFICULTY_MIN, DIFFICULTY_MAX
    )

    upsert_difficulty_rating(
        db,
        game_id,
        current_user.id,
        current_user.username,
        difficulty_level_id,
        ship_type_id,
        ratings,
        overall=None,
    )

    all_difficulty = db.query(models.DifficultyRating).filter_by(game_id=game_id).all()
    global_difficulty = get_global_difficulty_context(all_difficulty)
    if difficulty_level_id is None and ship_type_id is None:
        updated_context_data = global_difficulty
    else:
        updated_context_data = get_updated_difficulty_scores_for_context(
            db, game_id, difficulty_level_id, ship_type_id
        )

    overall_score = global_difficulty.get("overall_avg", 0.0)
    overall_realm = (
        get_difficulty_realm(overall_score).split(" ")[0]
        if overall_score > 0 else "N/A"
    )
    context_key = f"d{difficulty_level_id or 0}_s{ship_type_id or 0}"

    return JSONResponse(content={
        "status": "success",
        "message": "难度评分提交成功！",
        "updated_context_key": context_key,
        "updated_context_data": updated_context_data,
        "updated_overall": global_difficulty,
        "overall_difficulty_score": overall_score,
        "overall_difficulty_realm": overall_realm,
        "difficulty_ratings_count": len(all_difficulty),
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
    difficulty_level_id = parse_optional_context_id(
        params.get("difficulty_level_id"), "难度等级"
    )
    ship_type_id = parse_optional_context_id(
        params.get("ship_type_id"), "机体类型"
    )

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
    all_difficulty = db.query(models.DifficultyRating).filter_by(game_id=game_id).all()
    updated_overall = get_global_difficulty_context(all_difficulty)
    if difficulty_level_id is None and ship_type_id is None:
        updated_context_data = updated_overall
    else:
        updated_context_data = get_updated_difficulty_scores_for_context(
            db, game_id, difficulty_level_id, ship_type_id
        )

    overall_score = updated_overall.get("overall_avg", 0.0)
    overall_realm = (
        get_difficulty_realm(overall_score).split(" ")[0]
        if overall_score > 0 else "N/A"
    )
    context_key = f"d{difficulty_level_id or 0}_s{ship_type_id or 0}"

    return JSONResponse(content={
        "status": "success",
        "message": "已撤销你在该情境下的难度评分。",
        "updated_context_key": context_key,
        "updated_context_data": updated_context_data,
        "updated_overall": updated_overall,
        "overall_difficulty_score": overall_score,
        "overall_difficulty_realm": overall_realm,
    })