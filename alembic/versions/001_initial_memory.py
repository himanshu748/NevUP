"""001 — Create sessions and patterns tables.

Revision ID: 001_initial_memory
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial_memory"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── sessions table ───────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_user_tags", "sessions", ["user_id", "tags"])

    # ── patterns table ───────────────────────────────────────────────────
    op.create_table(
        "patterns",
        sa.Column(
            "pattern_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=True, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_patterns_user_id", "patterns", ["user_id"])
    op.create_index(
        "ix_patterns_user_signal", "patterns", ["user_id", "signal_type"]
    )


def downgrade() -> None:
    op.drop_table("patterns")
    op.drop_table("sessions")
