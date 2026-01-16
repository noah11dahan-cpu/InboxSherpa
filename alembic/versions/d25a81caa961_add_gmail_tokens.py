"""add gmail_tokens

Revision ID: d25a81caa961
Revises: 02e4fae3f50b
Create Date: 2026-01-15 22:47:59.582582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d25a81caa961"
down_revision: Union[str, Sequence[str], None] = "02e4fae3f50b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False, server_default="Bearer"),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index("ix_gmail_tokens_user_id", "gmail_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    # Safe downgrade: only drop if exists (DB may not have been upgraded properly before)
    op.execute("DROP INDEX IF EXISTS ix_gmail_tokens_user_id")
    op.execute("DROP TABLE IF EXISTS gmail_tokens")

