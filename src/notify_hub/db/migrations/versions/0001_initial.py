"""Subscriptions.

Revision ID: 0001
Revises:
Create Date: 2026-11-01 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_subscriptions_endpoint")),
    )
    op.create_index(op.f("ix_subscriptions_app"), "subscriptions", ["app"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_app"), table_name="subscriptions")
    op.drop_table("subscriptions")
