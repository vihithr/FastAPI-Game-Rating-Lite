"""add overall quick rating scores

Revision ID: 0004_rating_overall
Revises: 0003_user_token_version
Create Date: 2026-10-29
"""

from alembic import op

revision = "0004_rating_overall"
down_revision = "0003_user_token_version"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "quality_ratings", "overall"):
        op.execute("ALTER TABLE quality_ratings ADD COLUMN overall REAL")
    if not _has_column(bind, "difficulty_ratings", "overall"):
        op.execute("ALTER TABLE difficulty_ratings ADD COLUMN overall REAL")


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "difficulty_ratings", "overall"):
        op.execute("ALTER TABLE difficulty_ratings DROP COLUMN overall")
    if _has_column(bind, "quality_ratings", "overall"):
        op.execute("ALTER TABLE quality_ratings DROP COLUMN overall")
