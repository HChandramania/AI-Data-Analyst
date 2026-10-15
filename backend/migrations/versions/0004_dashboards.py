"""Saved dashboard references; evidence remains in owner-scoped analyses."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("dataset_versions_json", sa.Text(), nullable=False),
        sa.Column("cards_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dashboards_owner_id", "dashboards", ["owner_id"])


def downgrade():
    op.drop_table("dashboards")
