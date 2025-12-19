from fastapi import APIRouter, Depends, HTTPException, Request, Form, status, File, UploadFile
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from typing import Dict, Any
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from .. import models, database, auth
from app.config.templates import templates
from app.config.constants import BASE_DIR, MAX_TAGS_DISPLAY
from app.config.site_config import (
    get_stats_columns, get_quality_dimensions, get_difficulty_dimensions,
    get_quality_labels, get_difficulty_labels, get_quality_icon, get_difficulty_icon,
    get_ui_text, get_quality_min, get_quality_max, get_difficulty_min, get_difficulty_max,
    get_difficulty_realms, get_difficulty_max_score
)
from app.utils.ratings import get_game_evaluation
from pathlib import Path
import secrets
import shutil
import io

router = APIRouter(
    tags=["Pages"]
)
# --- 新增：处理标签的辅助函数 ---
def process_tags(db: Session, game: models.Game, tags_str: str):
    """处理以'|~|'分隔的标签字符串，更新游戏的多对多标签关系"""
    game.tags.clear()
    if not tags_str: return
    
    tag_names = {name.strip() for name in tags_str.split('|~|') if name.strip()}
    existing_tags = db.query(models.Tag).filter(models.Tag.name.in_(tag_names)).all()
    existing_tag_names = {tag.name for tag in existing_tags}
    game.tags.extend(existing_tags)
    for name in tag_names - existing_tag_names:
        new_tag = models.Tag(name=name)
        db.add(new_tag)
        game.tags.append(new_tag)

# --- 新增：处理一对多关系的通用辅助函数 ---
def process_one_to_many(db: Session, game: models.Game, items_str: str, model_class, relationship_name: str):
    """通用函数，用于处理别名、译名等一对多关系"""
    current_items = getattr(game, relationship_name)
    while current_items:
        db.delete(current_items.pop())
    if not items_str: return
    item_names = {name.strip() for name in items_str.split('|~|') if name.strip()}
    for name in item_names:
        current_items.append(model_class(name=name))


# --- 页面路由 ---

@router.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(database.get_db)):
    """主页"""
    # 最近添加的游戏（带封面）
    recent_games = db.query(models.Game).options(
        selectinload(models.Game.tags)
    ).order_by(models.Game.id.desc()).limit(6).all()
    
    # 热门游戏：基于品质评分，至少需要3条评分
    from ..models import game_tag_association
    games_with_ratings = db.query(
        models.Game.id,
        func.count(models.QualityRating.id).label('rating_count'),
        func.avg(
            (models.QualityRating.fun + 
             models.QualityRating.core + 
             models.QualityRating.depth + 
             models.QualityRating.performance + 
             models.QualityRating.story) / 5.0
        ).label('avg_score')
    ).join(
        models.QualityRating, models.Game.id == models.QualityRating.game_id
    ).group_by(
        models.Game.id
    ).having(
        func.count(models.QualityRating.id) >= 3
    ).order_by(
        func.avg(
            (models.QualityRating.fun + 
             models.QualityRating.core + 
             models.QualityRating.depth + 
             models.QualityRating.performance + 
             models.QualityRating.story) / 5.0
        ).desc()
    ).limit(8).all()
    
    # 处理热门游戏数据，添加评分信息，并加载tags关系
    popular_games = []
    for game_id, rating_count, avg_score in games_with_ratings:
        game = db.query(models.Game).options(
            selectinload(models.Game.tags)
        ).filter(models.Game.id == game_id).first()
        if game:
            game_data = {
                'game': game,
                'rating_count': rating_count,
                'avg_score': round(float(avg_score), 2) if avg_score else 0.0
            }
            popular_games.append(game_data)
    
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
    page: int = 1,
    per_page: int = 24
):
    """浏览所有游戏页面，支持按标签和公司筛选和分页"""
    
    # 确保页码有效
    page = max(1, page)
    per_page = max(1, min(100, per_page))  # 限制每页最多100条
    
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
    
    # 排序
    query = query.order_by(models.Game.title)

    # 获取总数（在应用分页之前）
    total_count = query.count()
    
    # 分页查询
    games = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # 计算总页数
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    # 查询所有的公司和标签用于前端筛选按钮
    companies = [c[0] for c in db.query(models.Game.company).distinct().order_by(models.Game.company).all()]
    
    # 优化：查询标签并计算每个标签的使用数量，按使用频率降序排序
    # 限制显示数量，只显示最常用的标签（由 MAX_TAGS_DISPLAY 配置）
    from sqlalchemy import func
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
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages
    })

@router.get("/stats", response_class=HTMLResponse)
def difficulty_stats(
    request: Request,
    db: Session = Depends(database.get_db)
):
    """难度评分统计页面"""
    from app.utils.ratings import get_difficulty_realm
    ui_text = get_ui_text()
    
    # 获取所有游戏及其难度评分
    games = db.query(models.Game).options(
        selectinload(models.Game.difficulty_ratings),
        selectinload(models.Game.difficulty_levels),
        selectinload(models.Game.ship_types),
        selectinload(models.Game.tags)
    ).order_by(models.Game.title).all()
    
    # 构建统计数据
    stats_data = []
    for game in games:
        # 按情境分组计算
        from itertools import groupby
        sort_key = lambda r: (r.difficulty_level_id or 0, r.ship_type_id or 0)
        
        for context_ids, ratings_iter in groupby(sorted(game.difficulty_ratings, key=sort_key), key=sort_key):
            diff_id, ship_id = context_ids
            ratings = list(ratings_iter)
            
            if not ratings:
                continue
            
            # 计算平均分（从配置动态读取维度字段）
            from app.config.site_config import get_difficulty_dimensions
            difficulty_dims = get_difficulty_dimensions()
            
            dim_scores = {}
            dim_avgs = {}
            for dim in difficulty_dims:
                field = dim["field"]
                scores = [getattr(r, field) for r in ratings if getattr(r, field) is not None]
                dim_scores[field] = scores
                dim_avgs[field] = sum(scores) / len(scores) if scores else 0
            
            valid_dims = sum(1 for scores in dim_scores.values() if scores)
            overall_avg = sum(dim_avgs.values()) / valid_dims if valid_dims > 0 else 0
            
            # 为了向后兼容，保留原有的字段名（如果配置中有这些字段）
            dodge_avg = dim_avgs.get("dodge", 0)
            strategy_avg = dim_avgs.get("strategy", 0)
            execution_avg = dim_avgs.get("execution", 0)
            
            # 获取难度等级和机体名称（从配置读取）
            difficulty_level_name = ui_text.get("difficulty_level", {}).get("overall", "游戏总体")
            if diff_id:
                diff_level = next((dl for dl in game.difficulty_levels if dl.id == diff_id), None)
                if diff_level:
                    difficulty_level_name = diff_level.name
            
            ship_type_name = ui_text.get("ship_type", {}).get("overall", "全机体/角色")
            if ship_id:
                ship = next((s for s in game.ship_types if s.id == ship_id), None)
                if ship:
                    ship_type_name = ship.name
            
            stats_data.append({
                "game_id": game.id,
                "game_title": game.title,
                "game_company": game.company,
                "tags": [t.name for t in game.tags],
                "difficulty_level_id": diff_id or 0,
                "difficulty_level_name": difficulty_level_name,
                "ship_type_id": ship_id or 0,
                "ship_type_name": ship_type_name,
                "dodge_avg": round(dodge_avg, 2),
                "strategy_avg": round(strategy_avg, 2),
                "execution_avg": round(execution_avg, 2),
                # 添加所有维度的平均值（动态，用于向后兼容）
                **{f"{dim['field']}_avg": round(dim_avgs.get(dim['field'], 0), 2) for dim in difficulty_dims},
                "overall_avg": round(overall_avg, 2),
                "realm": get_difficulty_realm(overall_avg),
                "rating_count": len(ratings)
            })
    
    # 获取所有游戏、难度等级、机体类型用于筛选
    all_games = db.query(models.Game).order_by(models.Game.title).all()
    all_difficulty_levels = db.query(models.DifficultyLevel).distinct().order_by(models.DifficultyLevel.name).all()
    all_ship_types = db.query(models.ShipType).distinct().order_by(models.ShipType.name).all()

    # 标签列表（仅包含有数据的标签）
    all_tags = sorted({tag for entry in stats_data for tag in entry["tags"]})
    all_companies = sorted({entry["game_company"] for entry in stats_data})
    
    # 从配置获取统计列名和UI文本
    stats_columns = get_stats_columns()
    
    return templates.TemplateResponse("difficulty_stats.html", {
        "request": request,
        "stats_data": stats_data,
        "all_games": all_games,
        "all_difficulty_levels": all_difficulty_levels,
        "all_ship_types": all_ship_types,
        "all_tags": all_tags,
        "all_companies": all_companies,
        "stats_columns": stats_columns,
        "ui_text": ui_text
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
    user_ratings = {"quality": None, "difficulty": {}}
    if request.state.user:
        # 获取用户的品质评分
        user_quality_rating = db.query(models.QualityRating).filter_by(
            game_id=game_id, user_id=request.state.user.id
        ).first()
        if user_quality_rating:
            user_ratings['quality'] = {
                'fun': user_quality_rating.fun,
                'core': user_quality_rating.core,
                'depth': user_quality_rating.depth,
                'performance': user_quality_rating.performance,
                'story': user_quality_rating.story
            }
        
        # 获取用户的所有难度评分（按情境分组）
        user_difficulty_ratings = db.query(models.DifficultyRating).filter_by(
            game_id=game_id, user_id=request.state.user.id
        ).all()
        if user_difficulty_ratings:
            user_ratings['difficulty'] = {}
            # 从配置获取难度维度字段名
            difficulty_dims = get_difficulty_dimensions()
            for rating in user_difficulty_ratings:
                context_key = f"d{rating.difficulty_level_id or 0}_s{rating.ship_type_id or 0}"
                rating_data = {
                    'difficulty_level_id': rating.difficulty_level_id,
                    'ship_type_id': rating.ship_type_id
                }
                for dim in difficulty_dims:
                    field = dim["field"]
                    rating_data[field] = getattr(rating, field, None)
                user_ratings['difficulty'][context_key] = rating_data
    
    # 获取配置数据传递给模板
    quality_dimensions = get_quality_dimensions()
    difficulty_dimensions = get_difficulty_dimensions()
    quality_labels = get_quality_labels()
    difficulty_labels = get_difficulty_labels()
    quality_icon = get_quality_icon()
    difficulty_icon = get_difficulty_icon()
    ui_text = get_ui_text()
    quality_min = get_quality_min()
    quality_max = get_quality_max()
    difficulty_min = get_difficulty_min()
    difficulty_max = get_difficulty_max()
    from app.config.site_config import get_difficulty_realms, get_difficulty_max_score
    difficulty_realms = get_difficulty_realms()
    difficulty_max_score = get_difficulty_max_score()
    
    return templates.TemplateResponse("game_details.html", {
        "request": request, 
        "game": game, 
        "evaluation": evaluation,
        "user_ratings": user_ratings,
        "quality_dimensions": quality_dimensions,
        "difficulty_dimensions": difficulty_dimensions,
        "quality_labels": quality_labels,
        "difficulty_labels": difficulty_labels,
        "quality_icon": quality_icon,
        "difficulty_icon": difficulty_icon,
        "ui_text": ui_text,
        "quality_min": quality_min,
        "quality_max": quality_max,
        "difficulty_min": difficulty_min,
        "difficulty_max": difficulty_max,
        "difficulty_realms": difficulty_realms,
        "difficulty_max_score": difficulty_max_score
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
        # 读取文件内容以检查大小
        contents = await image_file.read()
        file_size = len(contents)
        if file_size > 1 * 1024 * 1024: 
            raise HTTPException(status_code=413, detail="图片文件大小不能超过 1MB")
        if image_file.content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]: 
            raise HTTPException(status_code=400, detail="只支持上传 JPG, PNG, GIF, WebP 格式的图片")
        # 使用绝对路径
        upload_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
        upload_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        file_extension = Path(image_file.filename).suffix
        # 如果文件没有扩展名，根据content_type添加
        if not file_extension:
            content_type_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp"
            }
            file_extension = content_type_map.get(image_file.content_type, ".jpg")
        save_path = upload_dir / f"{token}{file_extension}"
        with open(save_path, "wb") as buffer:
            buffer.write(contents)
        image_path_to_db = f"/static/uploads/covers/{token}{file_extension}"

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
    except Exception as e:
        db.rollback()
        # 使用绝对路径删除图片
        if image_path_to_db:
            image_file_path = BASE_DIR / "app" / image_path_to_db.lstrip("/static/")
            if image_file_path.exists():
                image_file_path.unlink()
        raise HTTPException(status_code=500, detail=f"创建游戏失败: {e}")

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

    if image_file and image_file.filename:
        # 读取文件内容以检查大小
        contents = await image_file.read()
        file_size = len(contents)
        if file_size > 1 * 1024 * 1024: 
            raise HTTPException(status_code=413, detail="图片大小不能超过 1MB")
        if image_file.content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]: 
            raise HTTPException(status_code=400, detail="只支持 JPG, PNG, GIF, WebP 图片")
        old_image_path_str = game_to_update.image_url
        # 使用绝对路径
        upload_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
        upload_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        file_extension = Path(image_file.filename).suffix
        # 如果文件没有扩展名，根据content_type添加
        if not file_extension:
            content_type_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp"
            }
            file_extension = content_type_map.get(image_file.content_type, ".jpg")
        new_save_path = upload_dir / f"{token}{file_extension}"
        with open(new_save_path, "wb") as buffer:
            buffer.write(contents)
        game_to_update.image_url = f"/static/uploads/covers/{token}{file_extension}"
        # 使用绝对路径删除旧图片
        if old_image_path_str:
            old_image_file_path = BASE_DIR / "app" / old_image_path_str.lstrip("/static/")
            if old_image_file_path.exists():
                old_image_file_path.unlink()

    game_to_update.company, game_to_update.title, game_to_update.description = company, title, description
    process_tags(db, game_to_update, tags)
    process_one_to_many(db, game_to_update, translations, models.Translation, "translations")
    process_one_to_many(db, game_to_update, aliases, models.Alias, "aliases")
    process_one_to_many(db, game_to_update, difficulty_levels, models.DifficultyLevel, "difficulty_levels")
    process_one_to_many(db, game_to_update, ship_types, models.ShipType, "ship_types")
    db.commit()
    return RedirectResponse(url=f"/game/{game_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/user/{user_id}", response_class=HTMLResponse)
def user_profile(
    request: Request, 
    user_id: int, 
    db: Session = Depends(database.get_db),
    quality_page: int = 1,
    difficulty_page: int = 1,
    quality_per_page: int = 10,
    difficulty_per_page: int = 10
):
    """用户主页，显示用户的评分历史（支持分页）"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 确保页码有效
    quality_page = max(1, quality_page)
    difficulty_page = max(1, difficulty_page)
    quality_per_page = max(1, min(50, quality_per_page))  # 限制每页最多50条
    difficulty_per_page = max(1, min(50, difficulty_per_page))
    
    # 获取品质评分总数
    total_quality_count = db.query(models.QualityRating).filter(models.QualityRating.user_id == user_id).count()
    
    # 获取分页后的品质评分
    quality_ratings_query = db.query(models.QualityRating).options(
        selectinload(models.QualityRating.game).selectinload(models.Game.tags)
    ).filter(models.QualityRating.user_id == user_id).order_by(models.QualityRating.created_at.desc())
    
    quality_ratings = quality_ratings_query.offset((quality_page - 1) * quality_per_page).limit(quality_per_page).all()
    
    # 获取难度评分总数
    total_difficulty_count = db.query(models.DifficultyRating).filter(models.DifficultyRating.user_id == user_id).count()
    
    # 获取分页后的难度评分
    difficulty_ratings_query = db.query(models.DifficultyRating).options(
        selectinload(models.DifficultyRating.game).selectinload(models.Game.tags),
        selectinload(models.DifficultyRating.difficulty_level),
        selectinload(models.DifficultyRating.ship_type)
    ).filter(models.DifficultyRating.user_id == user_id).order_by(models.DifficultyRating.created_at.desc())
    
    difficulty_ratings = difficulty_ratings_query.offset((difficulty_page - 1) * difficulty_per_page).limit(difficulty_per_page).all()
    
    # 计算总页数
    quality_total_pages = (total_quality_count + quality_per_page - 1) // quality_per_page if total_quality_count > 0 else 1
    difficulty_total_pages = (total_difficulty_count + difficulty_per_page - 1) // difficulty_per_page if total_difficulty_count > 0 else 1
    
    # 计算平均品质评分（需要查询所有评分）
    all_quality_ratings = db.query(models.QualityRating).filter(models.QualityRating.user_id == user_id).all()
    avg_quality_score = 0.0
    if all_quality_ratings:
        total_score = sum((r.fun + r.core + r.depth + r.performance + r.story) / 5.0 for r in all_quality_ratings)
        avg_quality_score = round(total_score / len(all_quality_ratings), 2)
    
    # 计算平均难度评分（需要查询所有评分）
    all_difficulty_ratings = db.query(models.DifficultyRating).filter(models.DifficultyRating.user_id == user_id).all()
    avg_difficulty_score = 0.0
    if all_difficulty_ratings:
        # 从配置获取难度维度字段名
        difficulty_dims = get_difficulty_dimensions()
        total_difficulty = 0
        valid_count = 0
        for r in all_difficulty_ratings:
            dims = []
            for dim in difficulty_dims:
                field = dim["field"]
                value = getattr(r, field, None)
                if value is not None:
                    dims.append(value)
            if dims:
                total_difficulty += sum(dims) / len(dims)
                valid_count += 1
        if valid_count > 0:
            avg_difficulty_score = round(total_difficulty / valid_count, 2)
    
    # 获取配置数据传递给模板
    quality_dimensions = get_quality_dimensions()
    difficulty_dimensions = get_difficulty_dimensions()
    ui_text = get_ui_text()
    quality_icon = get_quality_icon()
    difficulty_icon = get_difficulty_icon()
    
    return templates.TemplateResponse("user_profile.html", {
        "request": request,
        "profile_user": user,
        "quality_ratings": quality_ratings,
        "difficulty_ratings": difficulty_ratings,
        "total_quality_ratings": total_quality_count,
        "total_difficulty_ratings": total_difficulty_count,
        "avg_quality_score": avg_quality_score,
        "avg_difficulty_score": avg_difficulty_score,
        "quality_page": quality_page,
        "difficulty_page": difficulty_page,
        "quality_per_page": quality_per_page,
        "difficulty_per_page": difficulty_per_page,
        "quality_total_pages": quality_total_pages,
        "difficulty_total_pages": difficulty_total_pages,
        "quality_dimensions": quality_dimensions,
        "difficulty_dimensions": difficulty_dimensions,
        "ui_text": ui_text,
        "quality_icon": quality_icon,
        "difficulty_icon": difficulty_icon
    })