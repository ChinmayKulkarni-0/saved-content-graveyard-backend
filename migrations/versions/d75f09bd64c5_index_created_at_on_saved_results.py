"""index created_at on saved_results

Revision ID: d75f09bd64c5
Revises: 4f8f3766921c
Create Date: 2026-09-09 03:16:39.657082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd75f09bd64c5'
down_revision: Union[str, None] = '4f8f3766921c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_saved_results_created_at", "saved_results", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_saved_results_created_at", table_name="saved_results")
