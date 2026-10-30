from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models


def process_tags(db: Session, game: models.Game, tags_str: str) -> None:
    """处理以 |~| 分隔的标签字符串，更新游戏的多对多标签关系。"""
    game.tags.clear()
    if not tags_str:
        return

    tag_names = {name.strip() for name in tags_str.split("|~|") if name.strip()}
    existing_tags = db.query(models.Tag).filter(models.Tag.name.in_(tag_names)).all()
    existing_tag_names = {tag.name for tag in existing_tags}
    game.tags.extend(existing_tags)
    for name in tag_names - existing_tag_names:
        game.tags.append(models.Tag(name=name))


def parse_pipe_names(items_str: str) -> List[str]:
    """解析以 |~| 分隔的名称，去空、去重并保留顺序。"""
    names = []
    seen = set()
    for raw_name in (items_str or "").split("|~|"):
        name = raw_name.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def process_one_to_many(
    db: Session,
    game: models.Game,
    items_str: str,
    model_class,
    relationship_name: str,
) -> None:
    """全量替换一对多关系，仅用于新建对象（无历史引用）。"""
    current_items = getattr(game, relationship_name)
    while current_items:
        db.delete(current_items.pop())
    for name in parse_pipe_names(items_str):
        current_items.append(model_class(name=name))


def sync_one_to_many(
    db: Session,
    game: models.Game,
    items_str: str,
    model_class,
    relationship_name: str,
    reference_model=None,
    reference_field: Optional[str] = None,
    item_label: str = "条目",
) -> None:
    """
    按名称增量同步一对多关系，保留已有行及其 ID。
    对难度等级、机体等被评分引用的对象，如果仍有评分引用则拒绝删除，
    避免历史评分丢失上下文。
    """
    desired_names = parse_pipe_names(items_str)
    desired_set = set(desired_names)
    current_items = list(getattr(game, relationship_name))
    current_names = {item.name for item in current_items}

    for item in current_items:
        if item.name in desired_set:
            continue
        if reference_model is not None and reference_field is not None:
            reference_column = getattr(reference_model, reference_field)
            reference_count = (
                db.query(reference_model.id)
                .filter(reference_column == item.id)
                .count()
            )
            if reference_count:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{item_label}“{item.name}”已有 {reference_count} 条评分引用，"
                        "无法删除；请先处理相关评分。"
                    ),
                )
        db.delete(item)

    for name in desired_names:
        if name not in current_names:
            getattr(game, relationship_name).append(model_class(name=name))
