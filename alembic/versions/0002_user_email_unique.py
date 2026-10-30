"""enforce case-insensitive unique user emails

Revision ID: 0002_user_email_unique
Revises: 0001_p1_constraints
Create Date: 2026-10-26
"""

from alembic import op

revision = "0002_user_email_unique"
down_revision = "0001_p1_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower "
        "ON users (lower(email))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower")
