"""init: pgvector extension, users, email_log

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text()),
        sa.Column("display_name", sa.String(80)),
        sa.Column("onboarding_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )

    op.create_table(
        "email_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_email_log"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_email_log_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key", name="uq_email_log_dedupe_key"),
    )
    op.create_index("ix_email_log_user_id", "email_log", ["user_id"])

    # defense in depth: the API connects as a privileged role; Supabase's anon/authenticated roles get nothing
    for table in ("users", "email_log"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_email_log_user_id", table_name="email_log")
    op.drop_table("email_log")
    op.drop_table("users")
