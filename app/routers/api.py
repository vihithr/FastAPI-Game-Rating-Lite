from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import List, Optional  # <-- 关键修改：导入 List 和 Optional
from .. import auth, models, database

router = APIRouter(
    prefix="/api/v1",
    tags=["API"]
)

# --- Schemas for data validation ---
class CommentUpdate(BaseModel):
    content: str

# --- 【修正】为API响应定义兼容Python 3.8的Pydantic模型 ---
class GameTagResponse(BaseModel):
    name: str
    class Config:
        from_attributes = True

class GameAliasResponse(BaseModel):
    name: str
    class Config:
        from_attributes = True

class GameBasicResponse(BaseModel):
    id: int
    title: str
    company: str
    image_url: Optional[str]  # <-- 关键修改：使用 Optional[str] 替代 str | None
    aliases: List[GameAliasResponse]
    tags: List[GameTagResponse]

    class Config:
        from_attributes = True

# --- API 路由 ---

@router.get("/games", response_model=List[GameBasicResponse])
def get_all_games_for_browse(db: Session = Depends(database.get_db)):
    """
    提供给前端浏览页面异步加载所有游戏数据。
    使用 selectinload 高效加载关联的别名和标签。
    """
    games = db.query(models.Game).options(
        selectinload(models.Game.aliases),
        selectinload(models.Game.tags)
    ).order_by(models.Game.title).all()
    return games


# --- Comment Routes ---

@router.post("/games/{game_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment_api(
    game_id: int,
    content: str = Form(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    [API] 添加评论 (仅限登录用户)
    """
    game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    new_comment = models.Comment(
        game_id=game_id, 
        content=content, 
        author_id=current_user.id,
        user_name=current_user.username 
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    
    return {
        "status": "success",
        "comment": {
            "id": new_comment.id,
            "content": new_comment.content,
            "user_name": new_comment.user_name,
            "user_id": new_comment.author_id
        }
    }

@router.put("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def update_comment_api(
    comment_id: int,
    comment_data: CommentUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    [API] 更新评论 (仅限评论作者本人)
    """
    comment_to_update = db.query(models.Comment).filter(models.Comment.id == comment_id).first()

    if not comment_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论未找到")
    
    if comment_to_update.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您没有权限编辑此评论")

    comment_to_update.content = comment_data.content
    db.commit()
    db.refresh(comment_to_update)

    return {
        "status": "success",
        "comment": {
            "id": comment_to_update.id,
            "content": comment_to_update.content,
            "user_name": comment_to_update.user_name,
            "user_id": comment_to_update.author_id
        }
    }

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment_api(
    comment_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    [API] 删除评论 (作者本人或管理员)
    """
    comment_to_delete = db.query(models.Comment).filter(models.Comment.id == comment_id).first()

    if not comment_to_delete:
        return

    is_author = comment_to_delete.author_id == current_user.id
    is_admin = current_user.is_admin

    if not (is_author or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您没有权限删除此评论")
        
    db.delete(comment_to_delete)
    db.commit()
    return

# --- Rating Routes ---

@router.get("/games/{game_id}/my-ratings")
def get_my_ratings(
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    [API] 获取当前用户对指定游戏的评分
    """
    user_ratings = {}
    
    # 获取品质评分
    quality_rating = db.query(models.QualityRating).filter_by(
        game_id=game_id, user_id=current_user.id
    ).first()
    if quality_rating:
        user_ratings['quality'] = {
            'fun': quality_rating.fun,
            'core': quality_rating.core,
            'depth': quality_rating.depth,
            'performance': quality_rating.performance,
            'story': quality_rating.story
        }
    
    # 获取所有难度评分
    difficulty_ratings = db.query(models.DifficultyRating).filter_by(
        game_id=game_id, user_id=current_user.id
    ).all()
    if difficulty_ratings:
        user_ratings['difficulty'] = {}
        for rating in difficulty_ratings:
            context_key = f"d{rating.difficulty_level_id or 0}_s{rating.ship_type_id or 0}"
            user_ratings['difficulty'][context_key] = {
                'dodge': rating.dodge,
                'strategy': rating.strategy,
                'execution': rating.execution,
                'difficulty_level_id': rating.difficulty_level_id,
                'ship_type_id': rating.ship_type_id
            }
    
    return {"status": "success", "ratings": user_ratings}