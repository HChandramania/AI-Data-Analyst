"""Owner-scoped search embeddings for saved evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_documents",
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_revision", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_documents_owner_id", "search_documents", ["owner_id"])


def downgrade():
    op.drop_table("search_documents")
