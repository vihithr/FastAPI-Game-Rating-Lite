"""add user token version for JWT revocation

Revision ID: 0003_user_token_version
Revises: 0002_user_email_unique
Create Date: 2026-10-26
"""

from alembic import op

revision = "0003_user_token_version"
down_revision = "0002_user_email_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN token_version")
