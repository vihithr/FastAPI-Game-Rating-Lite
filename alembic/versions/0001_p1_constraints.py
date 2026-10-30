"""add rating uniqueness and query indexes

Revision ID: 0001_p1_constraints
Revises:
Create Date: 2026-10-26
"""

from alembic import op

revision = "0001_p1_constraints"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quality_rating_game_user "
        "ON quality_ratings (game_id, user_id)"
    )
    # SQLite treats NULLs as distinct in UNIQUE indexes, so normalise the
    # optional difficulty context before enforcing one rating per context.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_difficulty_rating_context "
        "ON difficulty_ratings ("
        "game_id, user_id, "
        "COALESCE(difficulty_level_id, 0), "
        "COALESCE(ship_type_id, 0)"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_game_id ON comments (game_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quality_ratings_game_id "
        "ON quality_ratings (game_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_difficulty_ratings_game_id "
        "ON difficulty_ratings (game_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_difficulty_ratings_game_id")
    op.execute("DROP INDEX IF EXISTS ix_quality_ratings_game_id")
    op.execute("DROP INDEX IF EXISTS ix_comments_game_id")
    op.execute("DROP INDEX IF EXISTS uq_difficulty_rating_context")
    op.execute("DROP INDEX IF EXISTS uq_quality_rating_game_user")
