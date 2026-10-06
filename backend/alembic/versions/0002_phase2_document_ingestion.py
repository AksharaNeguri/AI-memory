"""phase 2 document ingestion

Revision ID: 0002_phase2_document_ingestion
Revises: 0001_initial_phase1
Create Date: 2026-10-05
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_phase2_document_ingestion"
down_revision: str | None = "0001_initial_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("documents", "metadata")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "file_size_bytes")
    op.drop_column("documents", "original_filename")
