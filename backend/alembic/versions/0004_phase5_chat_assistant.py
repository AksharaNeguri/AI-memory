"""phase 5 chat assistant

Revision ID: 0004_phase5_chat_assistant
Revises: 0003_phase3_embeddings_graph
Create Date: 2026-10-05
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_phase5_chat_assistant"
down_revision: str | None = "0003_phase3_embeddings_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("messages", "metadata")
