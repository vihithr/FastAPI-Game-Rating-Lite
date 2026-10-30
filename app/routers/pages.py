import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Form, status, File, UploadFile
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi.responses import RedirectResponse, HTMLResponse
from .. import models, database, auth
from app.config.templates import templates
from app.config.constants import BASE_DIR, MAX_TAGS_DISPLAY
from app.services.ratings import (
    build_user_ratings,
    get_difficulty_realm,
    get_difficulty_row_score,
    get_game_evaluation,
    get_quality_row_score,
    quality_row_score_expr,
)
from app.services.taxonomy import process_one_to_many, process_tags, sync_one_to_many
from app.services.uploads import cover_thumbnail_url, delete_static_file, save_cover_image

router = APIRouter(
    tags=["Pages"]
)
logger = logging.getLogger(__name__)

# --- 页面路由 ---

@router.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(database.get_db)):
    """主页"""
    # 最近添加的游戏（带封面）
    recent_games = db.query(models.Game).options(
        selectinload(models.Game.tags)
    ).order_by(models.Game.id.desc()).limit(6).all()
    
    # 热门游戏：基于品质评分，至少需要1条评分（社区规模小，阈值过高会导致榜单长期为空）
    from ..models import game_tag_association
    games_with_ratings = db.query(
        models.Game.id,
        func.count(models.QualityRating.id).label('rating_count'),
        func.avg(quality_row_score_expr()).label('avg_score')
    ).join(
        models.QualityRating, models.Game.id == models.QualityRating.game_id
    ).group_by(
        models.Game.id
    ).having(
        func.count(models.QualityRating.id) >= 1
    ).order_by(
        func.avg(quality_row_score_expr()).desc()
    ).limit(8).all()
    
    # 处理热门游戏数据，添加评分信息，并加载tags关系
    popular_games = []
    if games_with_ratings:
        ranked = {gid: (cnt, avg) for gid, cnt, avg in games_with_ratings}
        games = db.query(models.Game).options(
            selectinload(models.Game.tags)
        ).filter(models.Game.id.in_(ranked.keys())).all()
        by_id = {g.id: g for g in games}
        for game_id in ranked:
            game = by_id.get(game_id)
            if not game:
                continue
            rating_count, avg_score = ranked[game_id]
            popular_games.append({
                'game': game,
                'rating_count': rating_count,
                'avg_score': round(float(avg_score), 2) if avg_score else 0.0
            })
    
    # 平台统计数据
    total_games = db.query(func.count(models.Game.id)).scalar() or 0
    total_quality_ratings = db.query(func.count(models.QualityRating.id)).scalar() or 0
    total_difficulty_ratings = db.query(func.count(models.DifficultyRating.id)).scalar() or 0
    total_ratings = total_quality_ratings + total_difficulty_ratings
    total_users = db.query(func.count(models.User.id)).scalar() or 0
    
    # 热门标签（使用频率最高的标签）
    tags_with_count = db.query(
        models.Tag,
        func.count(game_tag_association.c.game_id).label('game_count')
    ).outerjoin(
        game_tag_association, models.Tag.id == game_tag_association.c.tag_id
    ).group_by(models.Tag.id).having(
        func.count(game_tag_association.c.game_id) > 0
    ).order_by(
        func.count(game_tag_association.c.game_id).desc(),
        models.Tag.name
    ).limit(15).all()
    
    popular_tags = [{"tag": tag, "count": count} for tag, count in tags_with_count]
    
    # 最近评论（可选，增加动态感）
    recent_comments = db.query(models.Comment).options(
        selectinload(models.Comment.game),
        selectinload(models.Comment.author)
    ).order_by(models.Comment.id.desc()).limit(5).all()
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "recent_games": recent_games,
        "popular_games": popular_games,
        "total_games": total_games,
        "total_ratings": total_ratings,
        "total_users": total_users,
        "popular_tags": popular_tags,
        "recent_comments": recent_comments
    })

@router.get("/games", response_class=HTMLResponse)
def browse_games(
    request: Request, 
    db: Session = Depends(database.get_db),
    tag: str = None,  # 单个标签（向后兼容）
    tags: str = None,  # 多个标签，用逗号分隔
    company: str = None,  # 公司筛选
    platform: str = None,  # 平台筛选（值形如「街机」「PC」）
    q: str = None,  # 关键词：标题、公司、别名、标签
    sort: str = "title-asc",
    page: int = 1,
    per_page: int = 24
):
    """浏览所有游戏页面，支持关键词、标签、公司筛选、排序和分页"""
    
    # 确保页码有效
    page = max(1, page)
    per_page = max(1, min(100, per_page))  # 限制每页最多100条
    search_query = (q or "").strip()
    sort = sort if sort in {"title-asc", "title-desc", "company-asc", "company-desc"} else "title-asc"
    
    # 处理标签筛选：支持单个tag（向后兼容）或多个tags
    active_tags = []
    if tags:
        # 多个标签，用逗号分隔
        active_tags = [t.strip() for t in tags.split(',') if t.strip()]
    elif tag:
        # 单个标签（向后兼容）
        active_tags = [tag]
    
    # 构建基础查询
    query = db.query(models.Game).options(selectinload(models.Game.tags))
    
    # 多标签筛选：游戏必须包含所有指定的标签
    if active_tags:
        # 使用子查询找到包含所有标签的游戏ID
        from ..models import game_tag_association
        tag_ids = db.query(models.Tag.id).filter(models.Tag.name.in_(active_tags)).all()
        tag_ids = [tid[0] for tid in tag_ids]
        
        if tag_ids:
            # 对每个标签，找到包含该标签的游戏ID集合
            game_id_sets = []
            for tid in tag_ids:
                game_ids = db.query(game_tag_association.c.game_id).filter(
                    game_tag_association.c.tag_id == tid
                ).distinct().all()
                game_id_sets.append({gid[0] for gid in game_ids})
            
            # 找到所有集合的交集（包含所有标签的游戏）
            if game_id_sets:
                common_game_ids = set.intersection(*game_id_sets)
                query = query.filter(models.Game.id.in_(common_game_ids))

    # 公司筛选
    if company:
        query = query.filter(models.Game.company == company)

    # 平台筛选：platform 列存的是「街机 / PC」这种多值串，用 like 匹配单个平台
    if platform:
        query = query.filter(models.Game.platform.ilike(f"%{platform}%"))

    # 关键词搜索：标题、公司、别名、标签
    if search_query:
        like_term = f"%{search_query}%"
        query = query.filter(
            or_(
                models.Game.title.ilike(like_term),
                models.Game.company.ilike(like_term),
                models.Game.aliases.any(models.Alias.name.ilike(like_term)),
                models.Game.tags.any(models.Tag.name.ilike(like_term)),
            )
        )

    # 排序
    if sort == "title-desc":
        query = query.order_by(func.lower(models.Game.title).desc())
    elif sort == "company-asc":
        query = query.order_by(
            func.lower(models.Game.company).asc(),
            func.lower(models.Game.title).asc(),
        )
    elif sort == "company-desc":
        query = query.order_by(
            func.lower(models.Game.company).desc(),
            func.lower(models.Game.title).asc(),
        )
    else:
        query = query.order_by(func.lower(models.Game.title).asc())

    # 获取总数并限制页码范围
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    page = min(page, total_pages)

    # 分页查询
    games = query.offset((page - 1) * per_page).limit(per_page).all()

    # 当前页作品的品质评分聚合（单次分组查询，供卡片徽标展示）
    rating_map = {}
    if games:
        rating_rows = db.query(
            models.QualityRating.game_id,
            func.count(models.QualityRating.id),
            func.avg(quality_row_score_expr())
        ).filter(
            models.QualityRating.game_id.in_([g.id for g in games])
        ).group_by(models.QualityRating.game_id).all()
        rating_map = {
            gid: {"count": cnt, "avg": round(float(avg), 1) if avg else 0.0}
            for gid, cnt, avg in rating_rows
        }
    
    # 查询所有的公司和标签用于前端筛选按钮
    companies = [c[0] for c in db.query(models.Game.company).distinct().order_by(models.Game.company).all()]

    # 平台筛选项：platform 列存的是「街机 / PC」这种多值串，拆开分别计数
    platform_counts: dict[str, int] = {}
    for (raw,) in db.query(models.Game.platform).filter(models.Game.platform.isnot(None)).all():
        for part in str(raw).split("/"):
            label = part.strip()
            if label:
                platform_counts[label] = platform_counts.get(label, 0) + 1
    platforms = sorted(platform_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    
    # 优化：查询标签并计算每个标签的使用数量，按使用频率降序排序
    # 限制显示数量，只显示最常用的标签（由 MAX_TAGS_DISPLAY 配置）
    from ..models import game_tag_association
    tags_with_count = db.query(
        models.Tag,
        func.count(game_tag_association.c.game_id).label('game_count')
    ).outerjoin(
        game_tag_association, models.Tag.id == game_tag_association.c.tag_id
    ).group_by(models.Tag.id).having(
        func.count(game_tag_association.c.game_id) > 0
    ).order_by(
        func.count(game_tag_association.c.game_id).desc(),
        models.Tag.name
    ).limit(MAX_TAGS_DISPLAY).all()
    
    # 构建标签列表，包含标签对象和使用数量
    all_tags = [{"tag": tag, "count": count} for tag, count in tags_with_count]

    return templates.TemplateResponse("browse_games.html", {
        "request": request,
        "games": games,
        "companies": companies,
        "all_tags": all_tags,
        "active_tags": active_tags,  # 当前激活的标签列表
        "current_company": company,  # 当前筛选的公司
        "current_platform": platform,  # 当前筛选的平台
        "platforms": platforms,  # [(平台名, 数量)]
        "search_query": search_query,
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "rating_map": rating_map
    })

@router.get("/stats", response_class=HTMLResponse)
def difficulty_stats(
    request: Request,
    db: Session = Depends(database.get_db)
):
    """难度全景统计页面。"""
    from datetime import datetime
    from itertools import groupby

    # 获取所有游戏及其难度评分
    games = db.query(models.Game).options(
        selectinload(models.Game.difficulty_ratings),
        selectinload(models.Game.difficulty_levels),
        selectinload(models.Game.ship_types),
        selectinload(models.Game.tags)
    ).order_by(models.Game.title).all()

    rows = []
    for game in games:
        sort_key = lambda rating: (rating.difficulty_level_id or 0, rating.ship_type_id or 0)

        for (diff_id, ship_id), ratings_iter in groupby(
            sorted(game.difficulty_ratings, key=sort_key), key=sort_key
        ):
            ratings = list(ratings_iter)
            if not ratings:
                continue

            dodge_scores = [r.dodge for r in ratings if r.dodge is not None]
            strategy_scores = [r.strategy for r in ratings if r.strategy is not None]
            execution_scores = [r.execution for r in ratings if r.execution is not None]
            row_scores = [
                score for score in (get_difficulty_row_score(r) for r in ratings)
                if score is not None
            ]
            if not row_scores:
                continue

            overall_avg = sum(row_scores) / len(row_scores)

            difficulty_level_name = "游戏总体"
            if diff_id:
                diff_level = next((dl for dl in game.difficulty_levels if dl.id == diff_id), None)
                if diff_level:
                    difficulty_level_name = diff_level.name

            ship_type_name = "全机体/角色"
            if ship_id:
                ship = next((s for s in game.ship_types if s.id == ship_id), None)
                if ship:
                    ship_type_name = ship.name

            rating_count = len(ratings)
            detailed_count = max(
                len(dodge_scores), len(strategy_scores), len(execution_scores)
            )

            rows.append({
                "game_id": game.id,
                "game_title": game.title,
                "company": game.company or "",
                "cover": cover_thumbnail_url(game.image_url, 400) or "",
                "tags": [tag.name for tag in game.tags],
                "difficulty_id": diff_id or 0,
                "difficulty_name": difficulty_level_name,
                "ship_id": ship_id or None,
                "ship_name": ship_type_name,
                "dodge": round(sum(dodge_scores) / len(dodge_scores), 2) if dodge_scores else None,
                "strategy": round(sum(strategy_scores) / len(strategy_scores), 2) if strategy_scores else None,
                "execution": round(sum(execution_scores) / len(execution_scores), 2) if execution_scores else None,
                "overall": round(overall_avg, 2),
                "count": rating_count,
                "detailed": detailed_count,
                "quick": max(0, rating_count - detailed_count),
                "dodge_n": len(dodge_scores),
                "strategy_n": len(strategy_scores),
                "execution_n": len(execution_scores),
            })

    game_ids = {row["game_id"] for row in rows}
    total_ratings = sum(row["count"] for row in rows)
    total_detailed = sum(row["detailed"] for row in rows)
    total_games = db.query(func.count(models.Game.id)).scalar() or 0
    last_rating_at = db.query(func.max(models.DifficultyRating.created_at)).scalar()
    updated = (
        last_rating_at.strftime("%Y-%m-%d")
        if last_rating_at
        else datetime.now().strftime("%Y-%m-%d")
    )

    mean_score = round(sum(row["overall"] for row in rows) / len(rows), 1) if rows else 0
    top_row = max(rows, key=lambda row: row["overall"]) if rows else None

    def realm_bucket(score: float) -> int:
        if score <= 10:
            return 0
        if score <= 20:
            return 1
        if score <= 30:
            return 2
        if score <= 40:
            return 3
        if score <= 55:
            return 4
        return 5

    payload = {
        "meta": {
            "total_games": total_games,
            "game_count": len(game_ids),
            "context_count": len(rows),
            "total_ratings": total_ratings,
            "total_detailed": total_detailed,
            "coverage_pct": round(len(game_ids) / total_games * 100) if total_games else 0,
            "realm_count": len({realm_bucket(row["overall"]) for row in rows}),
            "mean": mean_score,
            "mean_realm": get_difficulty_realm(mean_score).split(" ")[0] if rows else "—",
            "top_title": top_row["game_title"] if top_row else "—",
            "top_context": top_row["difficulty_name"] if top_row else "—",
            "top_score": round(top_row["overall"], 1) if top_row else 0,
            "updated": updated,
        },
        "rows": rows,
    }

    return templates.TemplateResponse("difficulty_stats.html", {
        "request": request,
        "stats_payload": payload,
    })

@router.get("/game/{game_id}", response_class=HTMLResponse)
def read_game(request: Request, game_id: int, db: Session = Depends(database.get_db)):
    """
    显示游戏详情页。
    使用 selectinload 优化查询，这是比 joinedload 更好的选择对于多个"to-many"关系。
    """
    game = db.query(models.Game).options(
        selectinload(models.Game.comments),
        selectinload(models.Game.tags),
        selectinload(models.Game.aliases),
        selectinload(models.Game.translations),
        selectinload(models.Game.difficulty_levels),
        selectinload(models.Game.ship_types),
        selectinload(models.Game.quality_ratings),
        selectinload(models.Game.difficulty_ratings)
    ).filter(models.Game.id == game_id).first()

    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    evaluation = get_game_evaluation(game)
    
    # 获取当前用户的评分（如果已登录）
    user_ratings = build_user_ratings(
        db,
        game_id,
        request.state.user.id if request.state.user else None,
    )
    
    similar_rows = (
        db.query(models.Game, func.avg(quality_row_score_expr()).label("avg_score"))
        .outerjoin(models.QualityRating, models.QualityRating.game_id == models.Game.id)
        .filter(
            models.Game.id != game.id,
            models.Game.company == game.company,
        )
        .group_by(models.Game.id)
        .order_by(func.avg(quality_row_score_expr()).desc())
        .limit(3)
        .all()
    )
    similar_games = [
        {
            "game": item,
            "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
        }
        for item, avg_score in similar_rows
    ]

    return templates.TemplateResponse("game_details.html", {
        "request": request, 
        "game": game, 
        "evaluation": evaluation,
        "user_ratings": user_ratings,
        "similar_games": similar_games,
    })

@router.get("/add-game", response_class=HTMLResponse)
async def show_add_game_form(request: Request):
    """显示添加游戏表单页面"""
    return templates.TemplateResponse("add_game.html", {"request": request})

@router.post("/add-game", response_class=RedirectResponse)
async def add_game(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
    company: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(None),
    tags: str = Form(""),
    translations: str = Form(""),
    aliases: str = Form(""),
    difficulty_levels: str = Form(""),
    ship_types: str = Form(""),
):
    """处理添加新游戏的表单提交"""
    image_path_to_db = None
    if image_file and image_file.filename:
        contents = await image_file.read()
        upload_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
        image_path_to_db = save_cover_image(image_file, contents, upload_dir)

    try:
        new_game = models.Game(company=company, title=title, description=description, image_url=image_path_to_db, created_by=current_user.id)
        process_tags(db, new_game, tags)
        process_one_to_many(db, new_game, translations, models.Translation, "translations")
        process_one_to_many(db, new_game, aliases, models.Alias, "aliases")
        process_one_to_many(db, new_game, difficulty_levels, models.DifficultyLevel, "difficulty_levels")
        process_one_to_many(db, new_game, ship_types, models.ShipType, "ship_types")
        db.add(new_game)
        db.commit()
        db.refresh(new_game)
        return RedirectResponse(url=f"/game/{new_game.id}", status_code=status.HTTP_303_SEE_OTHER)
    except IntegrityError:
        db.rollback()
        if image_path_to_db:
            delete_static_file(image_path_to_db)
        raise HTTPException(status_code=400, detail="游戏标题已存在，请更换标题")
    except SQLAlchemyError:
        db.rollback()
        if image_path_to_db:
            delete_static_file(image_path_to_db)
        logger.exception("创建游戏失败")
        raise HTTPException(status_code=500, detail="创建游戏失败，请稍后重试")
    except Exception:
        db.rollback()
        if image_path_to_db:
            delete_static_file(image_path_to_db)
        raise

@router.get("/game/{game_id}/edit", response_class=HTMLResponse)
async def show_edit_game_form(request: Request, game_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    """显示编辑游戏资料的表单页面（创建者或管理员）"""
    game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not game: raise HTTPException(status_code=404, detail="Game not found")
    
    # 检查权限：创建者或管理员
    is_owner = game.created_by == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限编辑该游戏")
    
    return templates.TemplateResponse("edit_game.html", {"request": request, "game": game})

@router.post("/game/{game_id}/update", response_class=RedirectResponse)
async def update_game(
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
    company: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),

    image_file: UploadFile = File(None),
    tags: str = Form(""),
    translations: str = Form(""),
    aliases: str = Form(""),
    difficulty_levels: str = Form(""),
    ship_types: str = Form(""),
):
    """处理更新游戏资料的表单提交（创建者或管理员）"""
    game_to_update = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not game_to_update: raise HTTPException(status_code=404, detail="Game not found")
    
    # 检查权限：创建者或管理员
    is_owner = game_to_update.created_by == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限编辑该游戏")

    # 先同步关联数据；如果删除被评分引用的难度/机体，会在写文件前直接报错
    process_tags(db, game_to_update, tags)
    sync_one_to_many(db, game_to_update, translations, models.Translation, "translations")
    sync_one_to_many(db, game_to_update, aliases, models.Alias, "aliases")
    sync_one_to_many(
        db,
        game_to_update,
        difficulty_levels,
        models.DifficultyLevel,
        "difficulty_levels",
        reference_model=models.DifficultyRating,
        reference_field="difficulty_level_id",
        item_label="难度等级",
    )
    sync_one_to_many(
        db,
        game_to_update,
        ship_types,
        models.ShipType,
        "ship_types",
        reference_model=models.DifficultyRating,
        reference_field="ship_type_id",
        item_label="机体/角色",
    )

    game_to_update.company, game_to_update.title, game_to_update.description = company, title, description

    old_image_path_str = game_to_update.image_url
    new_image_url = None
    if image_file and image_file.filename:
        contents = await image_file.read()
        upload_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
        new_image_url = save_cover_image(image_file, contents, upload_dir)
        game_to_update.image_url = new_image_url

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if new_image_url:
            delete_static_file(new_image_url)
        raise HTTPException(status_code=400, detail="游戏标题已存在，请更换标题")
    except SQLAlchemyError:
        db.rollback()
        if new_image_url:
            delete_static_file(new_image_url)
        logger.exception("更新游戏失败: id=%s", game_id)
        raise HTTPException(status_code=500, detail="更新游戏失败，请稍后重试")
    except Exception:
        db.rollback()
        if new_image_url:
            delete_static_file(new_image_url)
        raise

    # 提交成功后再删除旧图，避免事务失败时数据库指向已删除文件
    if new_image_url and old_image_path_str:
        delete_static_file(old_image_path_str)

    return RedirectResponse(url=f"/game/{game_id}", status_code=status.HTTP_303_SEE_OTHER)

def _profile_realm(score: float):
    if score <= 10:
        return 0, "见习"
    if score <= 20:
        return 1, "新手"
    if score <= 30:
        return 2, "入门"
    if score <= 40:
        return 3, "进阶"
    if score <= 55:
        return 4, "上级"
    return 5, "论外"


def _build_profile_payload(db: Session, user: models.User) -> dict:
    """个人评分档案页所需的完整聚合数据。"""
    quality_ratings = db.query(models.QualityRating).options(
        selectinload(models.QualityRating.game).selectinload(models.Game.tags)
    ).filter(models.QualityRating.user_id == user.id).order_by(
        models.QualityRating.created_at.desc()
    ).all()

    difficulty_ratings = db.query(models.DifficultyRating).options(
        selectinload(models.DifficultyRating.game).selectinload(models.Game.tags),
        selectinload(models.DifficultyRating.difficulty_level),
        selectinload(models.DifficultyRating.ship_type),
    ).filter(models.DifficultyRating.user_id == user.id).order_by(
        models.DifficultyRating.created_at.desc()
    ).all()

    def time_parts(value):
        if value is None:
            return "", "", ""
        return value.strftime("%Y-%m-%d"), value.strftime("%H:%M"), value.isoformat()

    def game_payload(game):
        return {
            "game_id": game.id,
            "title": game.title,
            "company": game.company or "",
            "cover": cover_thumbnail_url(game.image_url, 400) or "",
            "tags": [tag.name for tag in game.tags],
        }

    quality_rows = []
    for rating in quality_ratings:
        score = get_quality_row_score(rating)
        if score is None or rating.game is None:
            continue
        date, time_text, iso = time_parts(rating.created_at)
        mode = "quick" if rating.overall is not None else "detailed"
        dims = None
        if mode == "detailed":
            dims = {
                "fun": rating.fun,
                "core": rating.core,
                "depth": rating.depth,
                "performance": rating.performance,
                "story": rating.story,
            }
        row = game_payload(rating.game)
        row.update({
            "date": date,
            "time": time_text,
            "datetime": iso,
            "mode": mode,
            "overall": round(score, 2),
            "dims": dims,
        })
        quality_rows.append(row)

    difficulty_rows = []
    for rating in difficulty_ratings:
        score = get_difficulty_row_score(rating)
        if score is None or rating.game is None:
            continue
        date, time_text, iso = time_parts(rating.created_at)
        mode = "quick" if rating.overall is not None else "detailed"
        dims = None
        if mode == "detailed":
            dims = {
                "dodge": rating.dodge,
                "strategy": rating.strategy,
                "execution": rating.execution,
            }
        realm_index, realm_name = _profile_realm(score)
        row = game_payload(rating.game)
        row.update({
            "difficulty": rating.difficulty_level.name if rating.difficulty_level else "游戏总体",
            "ship": rating.ship_type.name if rating.ship_type else "全机体/角色",
            "date": date,
            "time": time_text,
            "datetime": iso,
            "mode": mode,
            "overall": round(score, 2),
            "dims": dims,
            "realm_index": realm_index,
            "realm": realm_name,
        })
        difficulty_rows.append(row)

    game_map = {}
    for row in quality_rows + difficulty_rows:
        game = game_map.get(row["game_id"])
        if game is None:
            game = {
                "game_id": row["game_id"],
                "title": row["title"],
                "company": row["company"],
                "cover": row["cover"],
                "tags": list(row["tags"]),
                "quality": None,
                "quality_mode": None,
                "difficulty_avg": None,
                "difficulty_realm": None,
                "difficulty_realm_index": None,
                "contexts": 0,
                "latest": "",
            }
            game_map[row["game_id"]] = game
        if row["datetime"] > game["latest"]:
            game["latest"] = row["datetime"]

    for row in quality_rows:
        game = game_map[row["game_id"]]
        game["quality"] = row["overall"]
        game["quality_mode"] = row["mode"]

    difficulty_by_game = {}
    for row in difficulty_rows:
        difficulty_by_game.setdefault(row["game_id"], []).append(row)
    for game_id, contexts in difficulty_by_game.items():
        scores = [row["overall"] for row in contexts]
        avg = round(sum(scores) / len(scores), 2) if scores else None
        realm_index, realm_name = _profile_realm(avg) if avg is not None else (None, None)
        game_map[game_id].update({
            "difficulty_avg": avg,
            "difficulty_realm": realm_name,
            "difficulty_realm_index": realm_index,
            "contexts": len(contexts),
        })

    games = list(game_map.values())
    games.sort(key=lambda game: (
        -(game["quality"] if game["quality"] is not None else -1),
        game["title"],
    ))

    groups = []
    for game_id, contexts in difficulty_by_game.items():
        contexts.sort(key=lambda row: row["overall"], reverse=True)
        avg = round(sum(row["overall"] for row in contexts) / len(contexts), 2)
        realm_index, realm_name = _profile_realm(avg)
        game = game_map[game_id]
        groups.append({
            "game_id": game_id,
            "title": game["title"],
            "company": game["company"],
            "cover": game["cover"],
            "tags": game["tags"],
            "quality": game["quality"],
            "difficulty_avg": avg,
            "realm": realm_name,
            "realm_index": realm_index,
            "contexts": contexts,
            "latest": max(row["datetime"] for row in contexts),
        })
    groups.sort(key=lambda group: group["latest"], reverse=True)

    quality_dims = []
    for key, label in [
        ("fun", "趣味性"), ("core", "核心设计"), ("depth", "深度"),
        ("performance", "演出"), ("story", "剧情"),
    ]:
        values = [
            row["dims"][key] for row in quality_rows
            if row["mode"] == "detailed" and row["dims"] and row["dims"].get(key) is not None
        ]
        quality_dims.append({
            "key": key, "label": label,
            "value": round(sum(values) / len(values), 2) if values else 0,
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "count": len(values),
        })

    difficulty_dims = []
    for key, label in [("dodge", "避弹"), ("strategy", "策略"), ("execution", "执行")]:
        values = [
            row["dims"][key] for row in difficulty_rows
            if row["mode"] == "detailed" and row["dims"] and row["dims"].get(key) is not None
        ]
        difficulty_dims.append({
            "key": key, "label": label,
            "value": round(sum(values) / len(values), 2) if values else 0,
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "count": len(values),
        })

    company_counts = {}
    tag_counts = {}
    for game in game_map.values():
        company_counts[game["company"]] = company_counts.get(game["company"], 0) + 1
        for tag in game["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    companies = [
        {"name": name, "count": count}
        for name, count in sorted(company_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    tags = [
        {"name": name, "count": count}
        for name, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]

    timeline = []
    for row in quality_rows:
        item = dict(row)
        item.update({"type": "quality", "score_max": 10})
        timeline.append(item)
    for row in difficulty_rows:
        item = dict(row)
        item.update({"type": "difficulty", "score_max": 60})
        timeline.append(item)
    timeline.sort(key=lambda item: item["datetime"], reverse=True)

    quality_count = len(quality_rows)
    difficulty_count = len(difficulty_rows)
    quality_avg = round(sum(row["overall"] for row in quality_rows) / quality_count, 2) if quality_count else 0
    difficulty_avg = round(sum(row["overall"] for row in difficulty_rows) / difficulty_count, 2) if difficulty_count else 0

    site_quality = db.query(func.avg(quality_row_score_expr())).scalar()
    site_quality_avg = round(float(site_quality), 2) if site_quality is not None else 0

    context_scores = {}
    for rating in db.query(models.DifficultyRating).all():
        score = get_difficulty_row_score(rating)
        if score is None:
            continue
        key = (rating.game_id, rating.difficulty_level_id or 0, rating.ship_type_id or 0)
        context_scores.setdefault(key, []).append(score)
    site_difficulty_values = [
        sum(values) / len(values) for values in context_scores.values() if values
    ]
    site_difficulty_avg = (
        round(sum(site_difficulty_values) / len(site_difficulty_values), 2)
        if site_difficulty_values else 0
    )

    detailed_count = (
        sum(1 for row in quality_rows if row["mode"] == "detailed") +
        sum(1 for row in difficulty_rows if row["mode"] == "detailed")
    )
    quick_count = (
        sum(1 for row in quality_rows if row["mode"] == "quick") +
        sum(1 for row in difficulty_rows if row["mode"] == "quick")
    )
    total_ratings = detailed_count + quick_count

    realm_counts = []
    for index, (name, color) in enumerate([
        ("见习", "#4dabf7"), ("新手", "#38d9a9"), ("入门", "#ffd43b"),
        ("进阶", "#ff922b"), ("上级", "#fa5252"), ("论外", "#b197fc"),
    ]):
        realm_counts.append({
            "name": name,
            "count": sum(1 for row in difficulty_rows if row["realm_index"] == index),
            "color": color,
        })

    hero_covers = []
    for game in games:
        if game["cover"] and game["quality"] is not None and game["quality"] >= 8:
            hero_covers.append(game["cover"])
        if len(hero_covers) >= 5:
            break
    if len(hero_covers) < 5:
        for game in games:
            if game["cover"] and game["cover"] not in hero_covers:
                hero_covers.append(game["cover"])
            if len(hero_covers) >= 5:
                break

    last_rated = max((row["datetime"] for row in quality_rows + difficulty_rows), default="")
    last_rated_date = last_rated[:10] if last_rated else (
        user.created_at.strftime("%Y-%m-%d") if user.created_at else "—"
    )

    top_company = companies[0] if companies else {"name": "—", "count": 0}
    top_tag = tags[0] if tags else {"name": "—", "count": 0}

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "joined": user.created_at.strftime("%Y-%m-%d") if user.created_at else "—",
            "is_admin": bool(user.is_admin),
        },
        "meta": {
            "quality_count": quality_count,
            "difficulty_count": difficulty_count,
            "game_count": len(game_map),
            "quality_avg": quality_avg,
            "difficulty_avg": difficulty_avg,
            "site_quality_avg": site_quality_avg,
            "site_difficulty_avg": site_difficulty_avg,
            "quality_delta": round(quality_avg - site_quality_avg, 2),
            "difficulty_delta": round(difficulty_avg - site_difficulty_avg, 2),
            "detailed_count": detailed_count,
            "quick_count": quick_count,
            "quality_detailed": sum(1 for row in quality_rows if row["mode"] == "detailed"),
            "quality_quick": sum(1 for row in quality_rows if row["mode"] == "quick"),
            "difficulty_detailed": sum(1 for row in difficulty_rows if row["mode"] == "detailed"),
            "difficulty_quick": sum(1 for row in difficulty_rows if row["mode"] == "quick"),
            "detailed_pct": round(detailed_count / total_ratings * 100) if total_ratings else 0,
            "top_company": top_company["name"],
            "top_company_count": top_company["count"],
            "top_tag": top_tag["name"],
            "top_tag_count": top_tag["count"],
            "last_rated": last_rated_date,
            "realm_counts": realm_counts,
        },
        "quality": quality_rows,
        "difficulty": difficulty_rows,
        "quality_dims": quality_dims,
        "difficulty_dims": difficulty_dims,
        "companies": companies,
        "tags": tags,
        "games": games,
        "difficulty_groups": groups,
        "timeline": timeline[:8],
        "hero_covers": hero_covers,
    }


@router.get("/user/{user_id}", response_class=HTMLResponse)
def user_profile(
    request: Request,
    user_id: int,
    db: Session = Depends(database.get_db),
):
    """用户评分档案页。"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    payload = _build_profile_payload(db, user)
    return templates.TemplateResponse("user_profile.html", {
        "request": request,
        "profile_payload": payload,
        "has_ratings": bool(payload["quality"] or payload["difficulty"]),
    })
