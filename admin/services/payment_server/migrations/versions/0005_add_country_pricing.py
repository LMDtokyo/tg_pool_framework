"""add per-country retail pricing overrides

Revision ID: payment_0005
Revises: payment_0004
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "payment_0005"
down_revision: Union[str, Sequence[str], None] = "payment_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_country_pricing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("markup_percent", sa.Numeric(24, 8), nullable=False),
        sa.Column("markup_fixed", sa.Numeric(24, 8), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country", name="uq_payment_country_pricing_country"),
    )


def downgrade() -> None:
    op.drop_table("payment_country_pricing")
