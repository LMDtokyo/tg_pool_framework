"""add retail pricing settings

Revision ID: payment_0004
Revises: payment_0003
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "payment_0004"
down_revision: Union[str, Sequence[str], None] = "payment_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_retail_pricing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("markup_percent", sa.Numeric(24, 8), nullable=False),
        sa.Column("markup_fixed", sa.Numeric(24, 8), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("payment_retail_pricing")
