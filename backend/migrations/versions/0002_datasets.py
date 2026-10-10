"""Owner-scoped immutable dataset metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("original_path", sa.String(255), nullable=False),
        sa.Column("parquet_path", sa.String(255), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])


def downgrade():
    op.drop_table("datasets")
