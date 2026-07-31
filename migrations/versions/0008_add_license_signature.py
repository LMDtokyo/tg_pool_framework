"""add signature column to license_state

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "license_state",
        sa.Column("signature", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("license_state", "signature")
