"""add platform / release_year / series to games

导入采集档案时，platform、年份、系列这些元数据没有对应的列可放，全被丢掉了。
这个迁移把三个字段补上，便于区分同一款游戏的不同平台版本，也支持按平台筛选、按年份排序。

Revision ID: 0005_game_meta
Revises: 0004_rating_overall
Create Date: 2026-10-31
"""

from alembic import op

revision = "0005_game_meta"
down_revision = "0004_rating_overall"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "games", "platform"):
        op.execute("ALTER TABLE games ADD COLUMN platform VARCHAR")
    if not _has_column(bind, "games", "release_year"):
        op.execute("ALTER TABLE games ADD COLUMN release_year INTEGER")
    if not _has_column(bind, "games", "series"):
        op.execute("ALTER TABLE games ADD COLUMN series VARCHAR")
    # 按平台筛选是高频操作，给个索引；年份排序数据量小，暂时不建
    op.execute("CREATE INDEX IF NOT EXISTS ix_games_platform ON games (platform)")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP INDEX IF EXISTS ix_games_platform")
    if _has_column(bind, "games", "series"):
        op.execute("ALTER TABLE games DROP COLUMN series")
    if _has_column(bind, "games", "release_year"):
        op.execute("ALTER TABLE games DROP COLUMN release_year")
    if _has_column(bind, "games", "platform"):
        op.execute("ALTER TABLE games DROP COLUMN platform")
