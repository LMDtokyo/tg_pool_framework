"""create scheduled_campaigns table

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("campaign_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("repeat_interval_hours", sa.Float(), nullable=True),
        sa.Column("max_occurrences", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("occurrences_run", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_campaigns_next_run_at", "scheduled_campaigns", ["next_run_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_campaigns_next_run_at", table_name="scheduled_campaigns")
    op.drop_table("scheduled_campaigns")
