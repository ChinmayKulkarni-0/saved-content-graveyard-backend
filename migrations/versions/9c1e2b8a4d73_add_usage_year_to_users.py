"""add usage_year to users

Revision ID: 9c1e2b8a4d73
Revises: d75f09bd64c5
Create Date: 2026-09-09 03:57:34.406749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c1e2b8a4d73'
down_revision: Union[str, None] = 'd75f09bd64c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("usage_year", sa.Integer(), server_default="0", nullable=True))


def downgrade() -> None:
    op.drop_column("users", "usage_year")
