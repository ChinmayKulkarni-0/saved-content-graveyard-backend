"""cascade delete saved_results on user delete

Revision ID: 4f8f3766921c
Revises: 445ecc6885e6
Create Date: 2026-09-09 03:02:49.543379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f8f3766921c'
down_revision: Union[str, None] = '445ecc6885e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("saved_results_user_id_fkey", "saved_results", type_="foreignkey")
    op.create_foreign_key(
        "saved_results_user_id_fkey",
        "saved_results",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("saved_results_user_id_fkey", "saved_results", type_="foreignkey")
    op.create_foreign_key(
        "saved_results_user_id_fkey",
        "saved_results",
        "users",
        ["user_id"],
        ["id"],
    )
