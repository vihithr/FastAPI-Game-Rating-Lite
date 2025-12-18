from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime

# +++ 新增：Game 和 Tag 的多对多关联表 +++
game_tag_association = Table('game_tag_association', Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

# --- 新增：Resource 和 ResourceTag 的多对多关联表（与游戏/悬赏标签完全隔离） ---
resource_tag_association = Table('resource_tag_association', Base.metadata,
    Column('resource_id', Integer, ForeignKey('resources.id'), primary_key=True),
    Column('resource_tag_id', Integer, ForeignKey('resource_tags.id'), primary_key=True)
)

# +++ 新增：Bounty 和 BountyTag 的多对多关联表 +++
bounty_tag_association = Table('bounty_tag_association', Base.metadata,
    Column('bounty_id', Integer, ForeignKey('bounties.id'), primary_key=True),
    Column('bounty_tag_id', Integer, ForeignKey('bounty_tags.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    comments = relationship("Comment", back_populates="author")
    bounties = relationship("Bounty", back_populates="creator")
    bounty_comments = relationship("BountyComment", back_populates="author")

    # 资源上传记录（仅反向关系，资源模型中包含 uploader_id 外键）
    resources = relationship("Resource", back_populates="uploader")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    user = relationship("User")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True, nullable=False)
    company = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # --- 原有的 aliases, translations, difficulty_levels, ship_types 等字段已被移除 ---
    
    comments = relationship("Comment", back_populates="game", cascade="all, delete-orphan")
    quality_ratings = relationship("QualityRating", back_populates="game", cascade="all, delete-orphan")
    difficulty_ratings = relationship("DifficultyRating", back_populates="game", cascade="all, delete-orphan")

    # +++ 新增：使用关系来管理标签、别名等 +++
    tags = relationship("Tag", secondary=game_tag_association, back_populates="games", lazy="selectin")
    aliases = relationship("Alias", back_populates="game", cascade="all, delete-orphan", lazy="selectin")
    translations = relationship("Translation", back_populates="game", cascade="all, delete-orphan", lazy="selectin")
    difficulty_levels = relationship("DifficultyLevel", back_populates="game", cascade="all, delete-orphan", lazy="selectin")
    ship_types = relationship("ShipType", back_populates="game", cascade="all, delete-orphan", lazy="selectin")


# +++ 新增：标签模型 +++
class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    games = relationship("Game", secondary=game_tag_association, back_populates="tags")


# --- 新增：资源标签模型（独立于游戏标签与悬赏标签） ---
class ResourceTag(Base):
    __tablename__ = "resource_tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    resources = relationship("Resource", secondary="resource_tag_association", back_populates="tags", lazy="selectin")

# +++ 新增：别名模型 +++
class Alias(Base):
    __tablename__ = "aliases"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", back_populates="aliases")

# +++ 新增：译名模型 +++
class Translation(Base):
    __tablename__ = "translations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", back_populates="translations")

# +++ 新增：难度等级模型 +++
class DifficultyLevel(Base):
    __tablename__ = "difficulty_levels"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", back_populates="difficulty_levels")
    ratings = relationship("DifficultyRating", back_populates="difficulty_level")

# +++ 新增：机体/角色模型 +++
class ShipType(Base):
    __tablename__ = "ship_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", back_populates="ship_types")
    ratings = relationship("DifficultyRating", back_populates="ship_type")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    content = Column(String)
    user_name = Column(String, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), index=True)
    author = relationship("User", back_populates="comments")
    game = relationship("Game", back_populates="comments")
    
class QualityRating(Base):
    __tablename__ = "quality_ratings"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_name = Column(String)
    fun = Column(Integer)
    core = Column(Integer)
    depth = Column(Integer)
    performance = Column(Integer)
    story = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    game = relationship("Game", back_populates="quality_ratings")


class DifficultyRating(Base):
    __tablename__ = "difficulty_ratings"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_name = Column(String)
    
    # +++ 新增字段 +++
    difficulty_level_id = Column(Integer, ForeignKey("difficulty_levels.id"), nullable=True, index=True)
    ship_type_id = Column(Integer, ForeignKey("ship_types.id"), nullable=True, index=True)
    
    dodge = Column(Integer)
    strategy = Column(Integer)
    execution = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    game = relationship("Game", back_populates="difficulty_ratings")
    
    # +++ 新增关系 +++
    difficulty_level = relationship("DifficultyLevel", back_populates="ratings")
    ship_type = relationship("ShipType", back_populates="ratings")


# --- 新增：文章/静态页模型 ---
class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    content_md = Column(Text, nullable=True)
    content_html = Column(Text, nullable=True)
    status = Column(String, default="published", nullable=False)  # 仅管理员发布
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    static_path = Column(String, nullable=True)  # 相对路径 /static/articles/{slug}/
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author = relationship("User")

# --- 新增：悬赏板块模型 ---
class BountyCategory(Base):
    __tablename__ = "bounty_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    bounties = relationship("Bounty", back_populates="category")

# --- 新增：悬赏标签模型（独立于游戏标签） ---
class BountyTag(Base):
    __tablename__ = "bounty_tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    bounties = relationship("Bounty", secondary="bounty_tag_association", back_populates="bounty_tags", lazy="selectin")

# --- 新增：悬赏模型 ---
class Bounty(Base):
    __tablename__ = "bounties"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    reward = Column(String, nullable=False)  # 悬赏金额或奖品描述
    game_name = Column(String, nullable=True, index=True)  # 游戏悬赏（文本字段，不需要关联Game模型）
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("bounty_categories.id"), nullable=False, index=True)
    contact_info = Column(String, nullable=True)  # 联系方式
    is_completed = Column(Boolean, default=False, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    creator = relationship("User", back_populates="bounties")
    category = relationship("BountyCategory", back_populates="bounties")
    bounty_tags = relationship("BountyTag", secondary="bounty_tag_association", back_populates="bounties", lazy="selectin")
    comments = relationship("BountyComment", back_populates="bounty", cascade="all, delete-orphan", order_by="BountyComment.created_at.desc()")

# --- 新增：悬赏评论模型 ---
class BountyComment(Base):
    __tablename__ = "bounty_comments"
    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    bounty = relationship("Bounty", back_populates="comments")
    author = relationship("User", back_populates="bounty_comments")


# --- 新增：资源索引系统模型 ---
class Resource(Base):
    """
    资源表（与游戏、悬赏完全独立）：
    - tags 使用独立的 ResourceTag，多对多关系
    - status 使用字符串枚举语义：valid / invalid
    """
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)  # 提交内容/正文，包含网盘链接、提取码等
    intro = Column(Text, nullable=True)
    cover_image = Column(String, nullable=True)  # 静态文件路径
    category = Column(String, nullable=False, index=True)  # 如：游戏本体 / 补丁 / OST
    status = Column(String, default="valid", nullable=False, index=True)  # valid / invalid
    heat = Column(Integer, default=0, nullable=False, index=True)

    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    uploader = relationship("User", back_populates="resources")
    tags = relationship("ResourceTag", secondary=resource_tag_association, back_populates="resources", lazy="selectin")


class ResourceVote(Base):
    """
    资源投票表：限制每个用户对每个资源只能投一票。
    value: 1 表示顶，-1 表示踩
    """
    __tablename__ = "resource_votes"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_resource_vote_user_resource"),
    )

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    value = Column(Integer, nullable=False)  # 1 或 -1
    created_at = Column(DateTime(timezone=True), server_default=func.now())

