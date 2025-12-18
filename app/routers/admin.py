# app/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models, database, auth
from app.config.constants import BASE_DIR

router = APIRouter(
    prefix="/admin",  # 所有此文件的路由都以 /admin 开头
    tags=["Admin"]    # 在API文档中分组
)

@router.delete("/comment/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment_by_admin(
    comment_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user) # <-- 权限保护
):
    """管理员删除任意评论"""
    comment_to_delete = db.query(models.Comment).filter(models.Comment.id == comment_id).first()

    if not comment_to_delete:
        # 即使找不到，也返回成功，因为最终结果（评论不存在）是一致的
        return

    db.delete(comment_to_delete)
    db.commit()
    return

@router.delete("/game/{game_id}", status_code=status.HTTP_200_OK)
async def delete_game_by_admin(
    game_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user) # <-- 权限保护
):
    """
    管理员删除整个游戏及其所有关联数据（评分、评论、封面文件）。
    这是一个危险操作。
    """
    game_to_delete = db.query(models.Game).filter(models.Game.id == game_id).first()

    if not game_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到该游戏")

    # 1. 删除封面图片文件（使用绝对路径）
    if game_to_delete.image_url:
        image_file_path = BASE_DIR / "app" / game_to_delete.image_url.lstrip("/static/")
        if image_file_path.exists():
            image_file_path.unlink()
    
    # 2. 删除游戏记录
    # 由于在 Game 模型中设置了 cascade="all, delete-orphan"，
    # SQLAlchemy 会自动删除所有与此游戏关联的评论和（通用）评分。
    # 我们还需要手动删除 QualityRating 和 DifficultyRating。
    db.query(models.QualityRating).filter(models.QualityRating.game_id == game_id).delete()
    db.query(models.DifficultyRating).filter(models.DifficultyRating.game_id == game_id).delete()
    
    db.delete(game_to_delete)
    db.commit()
    
    # 清理无引用的标签（可选：在删除游戏后自动清理）
    # cleanup_orphaned_tags(db)

    return {"status": "success", "message": f"游戏 '{game_to_delete.title}' 已被成功删除。"}

@router.post("/cleanup-orphaned-tags", status_code=status.HTTP_200_OK)
async def cleanup_orphaned_tags_endpoint(
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(auth.get_current_admin_user)
):
    """
    清理所有无引用的标签（没有任何游戏使用的标签）。
    这是一个维护操作，建议定期执行。
    """
    return cleanup_orphaned_tags(db)

def cleanup_orphaned_tags(db: Session):
    """
    清理无引用的标签。
    返回被删除的标签数量和标签名称列表。
    """
    from ..models import game_tag_association
    # 查找所有没有任何游戏关联的标签
    orphaned_tags = db.query(models.Tag).outerjoin(
        game_tag_association
    ).filter(
        game_tag_association.c.game_id == None
    ).all()
    
    deleted_count = len(orphaned_tags)
    deleted_names = [tag.name for tag in orphaned_tags]
    
    # 删除这些标签
    for tag in orphaned_tags:
        db.delete(tag)
    
    db.commit()
    
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "deleted_tags": deleted_names,
        "message": f"已清理 {deleted_count} 个无引用的标签。" if deleted_count > 0 else "没有需要清理的无引用标签。"
    }